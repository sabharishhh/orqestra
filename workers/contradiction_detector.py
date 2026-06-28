"""
5-Level Contradiction Detection Funnel (multi-tenant).

Sprint 3.1 refactor: every magic number now reads from services.
The detection structure — bootstrap gate (F1.1), Level 0 OBG variance,
Level 1 vector clock concurrency, Level 3 HNSW neighbor search, Level 4
NLI classification, Level 5 DSPy apex judge — is unchanged. Only the
thresholds, NLI floors, dedup windows, severity buckets, and cost
coefficients are now per-org config instead of hardcoded constants.
"""
import os
import logging
from observability import get_logger
import dspy
import numpy as np
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

from core.database import SessionLocal
from models.database import Claim, Contradiction, EntityBeliefState, System
from services.nli_classifier import classify_pair
from services.config_loader import get_org_config
from services.severity_scorer import calculate_severity_and_cost
from services.threshold_service import get_thresholds_for_entity

logger = get_logger(__name__)


# ==========================================
# MATH & UTILS
# ==========================================
def calculate_cosine_distance(emb1, emb2):
    """Calculates cosine distance between two raw vector arrays."""
    if emb1 is None or emb2 is None or len(emb1) == 0 or len(emb2) == 0:
        return 1.0

    a = np.array(emb1)
    b = np.array(emb2)

    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 1.0

    return float(1.0 - (np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))


# ==========================================
# LEVEL 5: DSPy APEX JUDGE (COMPILED BRAIN)
# ==========================================
turbo = dspy.LM('openai/gpt-5.4-mini', api_key=os.environ.get("OPENAI_API_KEY"))
dspy.settings.configure(lm=turbo)


class EnterpriseContradictionSignature(dspy.Signature):
    """Evaluate if two claims logically contradict each other. Pay strict attention to conditional constraints (e.g., 'only if', 'unless', 'strictly avoid'). If one statement is conditional and the other is a general rule, they might NOT contradict."""
    claim_a = dspy.InputField(desc="First claim from System A")
    claim_b = dspy.InputField(desc="Second claim from System B")
    topic = dspy.InputField(desc="The core entity or topic being discussed")

    extracted_entities = dspy.OutputField(desc="Extract entities involved")
    extracted_conditions = dspy.OutputField(desc="Extract conditional constraints from both claims")
    extracted_actions = dspy.OutputField(desc="Extract prescribed actions from both claims")
    is_contradiction = dspy.OutputField(desc="Return strictly 'True' if they inherently contradict in all scenarios, or 'False' if they are conditionally compatible.")


class ApexJudge(dspy.Module):
    def __init__(self):
        super().__init__()
        self.judge = dspy.ChainOfThought(EnterpriseContradictionSignature)

    def forward(self, claim_a, claim_b, topic):
        return self.judge(claim_a=claim_a, claim_b=claim_b, topic=topic)


apex_judge = ApexJudge()

compiled_brain_path = os.path.join(os.path.dirname(__file__), "..", "models", "apex_compiled", "optimized_config.json")
if os.path.exists(compiled_brain_path):
    try:
        logger.info("🧠 Loading compiled DSPy brain weights...")
        apex_judge.load(compiled_brain_path)
        logger.info("✅ DSPy brain successfully loaded.")
    except Exception as e:
        logger.warning(f"⚠️ Failed to load compiled DSPy brain (version mismatch): {e}. Running in Zero-Shot fallback mode.")
else:
    logger.warning("⚠️ Compiled DSPy brain not found. Running in Zero-Shot fallback mode.")


# ==========================================
# VECTOR CLOCK CAUSALITY (LEVEL 1)
# ==========================================
def is_concurrent(clock_a: dict, clock_b: dict) -> bool:
    """LEVEL 1 MATH: Two vector clocks are concurrent (no happens-before relation)."""
    if not clock_a or not clock_b:
        return True
    if clock_a == clock_b:
        return False  # ISSUE-12: equal clocks represent identical logical state, not concurrency
    if not set(clock_a.keys()).intersection(set(clock_b.keys())):
        return True

    a_leq_b = True
    b_leq_a = True
    all_keys = set(clock_a.keys()).union(set(clock_b.keys()))

    for k in all_keys:
        val_a = clock_a.get(k, 0)
        val_b = clock_b.get(k, 0)
        if val_a > val_b:
            a_leq_b = False
        if val_b > val_a:
            b_leq_a = False

    return not (a_leq_b or b_leq_a)


# ==========================================
# F2.5 SEMANTIC CLUSTER SUPPRESSION
# ==========================================
def has_active_semantic_conflict(
    db: Session,
    new_claim_embedding: list,
    entity_hint: str,
    suppression_distance: float,
) -> bool:
    """F2.5: Smart Semantic Cluster Suppression.

    Threshold (suppression_distance) is now per-org config rather than a
    hardcoded 0.05. Defaults to 0.05 in DetectionConfig.
    """
    open_contras = db.query(Contradiction).join(
        Claim, Contradiction.claim_a_id == Claim.id
    ).filter(
        Claim.entity_hint == entity_hint,
        Contradiction.status == 'open'
    ).all()

    for c in open_contras:
        claim_a = db.query(Claim).filter(Claim.id == c.claim_a_id).first()
        if claim_a and claim_a.embedding is not None and len(claim_a.embedding) > 0:
            if calculate_cosine_distance(new_claim_embedding, claim_a.embedding) <= suppression_distance:
                return True
    return False


# ==========================================
# ORG_ID RESOLUTION
# ==========================================
def _resolve_org_id_from_system(db: Session, system_id: str) -> str:
    """
    Look up org_id for a system_id. Single query, cached per-funnel-run
    via the org_id_cache dict in run_5_level_funnel.
    """
    row = db.query(System.org_id).filter(System.id == system_id).first()
    if row is None:
        raise RuntimeError(f"System {system_id} has no org_id — Sprint 1.3 backfill missing?")
    return str(row.org_id)


# ==========================================
# MAIN FUNNEL
# ==========================================
def run_5_level_funnel(system_id: str, updated_entities: list) -> list:
    """
    Worker 4 Phase: 5-Level Detection Funnel, fully tenant-scoped.

    Reads all tuning parameters from per-org config services:
      - bootstrap_min_samples         (DetectionConfig)
      - level_0_cosine / level_3_cosine (per-category in CategoryThreshold)
      - nli_confidence_floor          (per-category w/ org-level fallback)
      - semantic_suppression_distance (DetectionConfig)
      - regression_dedup_days         (DetectionConfig)
      - severity_tier / cost_usd      (per-CanonicalEntity via severity_scorer)
    """
    if not updated_entities:
        return []

    db: Session = SessionLocal()
    contradiction_ids = []

    try:
        # Resolve org_id once per funnel invocation
        org_id = _resolve_org_id_from_system(db, system_id)
        cfg = get_org_config(org_id, db)

        new_claims = db.query(Claim).filter(
            Claim.system_id == system_id,
            Claim.entity_hint.in_(updated_entities)
        ).all()

        for new_claim in new_claims:

            # Per-entity threshold profile (Level 0, 3, NLI floor)
            thresholds = get_thresholds_for_entity(org_id, new_claim.entity_hint, db)

            # --- F1.1 BOOTSTRAP GATE ---
            # Spec: when claim_count < bootstrap_min_samples, skip Levels 0 & 1
            # (OBG centroid + vector clock) and enter at Level 3. Do NOT skip
            # detection entirely.
            sys_obg = db.query(EntityBeliefState).filter_by(
                system_id=system_id,
                entity_name=new_claim.entity_hint
            ).first()

            is_bootstrapping = (
                not sys_obg or sys_obg.sample_count < cfg.bootstrap_min_samples
            )

            # Candidate pool for Level 3 — historical claims from OTHER systems
            # in the SAME ORG for this entity. Cross-org leakage is impossible.
            all_other_claims = db.query(Claim).filter(
                Claim.org_id == org_id,
                Claim.system_id != system_id,
                Claim.entity_hint == new_claim.entity_hint
            ).all()

            if not all_other_claims:
                logger.info(f"No cross-system claims for '{new_claim.entity_hint}'. Skipping.")
                continue

            if is_bootstrapping:
                logger.info(
                    f"F1.1 Bootstrap: '{new_claim.entity_hint}' < {cfg.bootstrap_min_samples} samples "
                    f"for system {system_id}. Bypassing Levels 0 & 1, entering at Level 3."
                )
                level3_candidates = all_other_claims
            else:
                # --- LEVEL 0: OBG CENTROID VARIANCE ---
                # Threshold is per-category (e.g. consumer=0.40, clinical=0.25)
                # instead of the previous hardcoded 0.35.
                other_obgs = db.query(EntityBeliefState).filter(
                    EntityBeliefState.org_id == org_id,
                    EntityBeliefState.entity_name == new_claim.entity_hint,
                    EntityBeliefState.system_id != system_id
                ).all()

                if other_obgs:
                    diverges = False
                    for obg in other_obgs:
                        if obg.sample_count < cfg.bootstrap_min_samples:
                            continue
                        dist = calculate_cosine_distance(new_claim.embedding, obg.centroid_embedding)
                        if dist > thresholds.level_0_cosine:
                            diverges = True
                            break

                    if not diverges:
                        logger.info(
                            f"LEVEL 0: Claim does not diverge (>{thresholds.level_0_cosine}) "
                            f"from any other system's OBG for '{new_claim.entity_hint}'. Dropped."
                        )
                        continue

                # --- LEVEL 1: VECTOR CLOCK CAUSALITY ---
                concurrent_claims = []
                for hist in all_other_claims:
                    if is_concurrent(new_claim.vector_clock, hist.vector_clock):
                        concurrent_claims.append(hist)
                    else:
                        logger.info(
                            f"LEVEL 1: Chronological update detected for '{new_claim.entity_hint}'. Dropped."
                        )

                if not concurrent_claims:
                    continue

                level3_candidates = concurrent_claims

            # --- LEVEL 3: HNSW VECTOR SEARCH ---
            # Per-category threshold (consumer=0.45, clinical=0.30) instead of 0.40.
            close_neighbors = []
            for neighbor in level3_candidates:
                dist = calculate_cosine_distance(new_claim.embedding, neighbor.embedding)
                if dist <= thresholds.level_3_cosine:
                    close_neighbors.append((neighbor, dist))

            for neighbor, distance in close_neighbors:

                # --- F2.5 Semantic Cluster Suppression ---
                if has_active_semantic_conflict(
                    db,
                    new_claim.embedding,
                    new_claim.entity_hint,
                    cfg.semantic_suppression_distance,
                ):
                    logger.info(
                        f"🛡️ Alert Suppressed: Semantic cluster for '{new_claim.entity_hint}' "
                        f"already has an active ticket."
                    )
                    continue

                claim_a_str = f"{new_claim.subject} {new_claim.predicate} {new_claim.object}"
                claim_b_str = f"{neighbor.subject} {neighbor.predicate} {neighbor.object}"

                # --- LEVEL 4: NLI CLASSIFICATION ---
                # NLI floor is per-category (clinical 0.60, consumer 0.70) with
                # org-level fallback. Lower floors for high-stakes domains where
                # missing a contradiction is more costly than a false positive.
                result = classify_pair(claim_a_str, claim_b_str)

                if result["prediction"] == "CONTRADICTION" and result["confidence"] >= thresholds.nli_floor:

                    # --- LEVEL 5: DSPY APEX JUDGE ---
                    try:
                        apex_res = apex_judge(
                            claim_a=claim_a_str,
                            claim_b=claim_b_str,
                            topic=new_claim.entity_hint,
                        )
                        if "true" not in str(apex_res.is_contradiction).lower():
                            logger.info(
                                f"⚖️ Apex Judge Override: NLI flagged '{new_claim.entity_hint}', "
                                f"but DSPy found conditional compatibility. Alert dropped."
                            )
                            continue
                    except Exception as apex_err:
                        logger.error(f"Apex Judge failed, falling back to NLI verdict: {apex_err}")

                    id_a, id_b = sorted([str(new_claim.id), str(neighbor.id)])

                    # --- REG-05: Time-bounded regression dedup ---
                    # Window is per-org (e.g. clinical: 14 days, consumer: 7).
                    recent_open = db.query(Contradiction).filter(
                        Contradiction.claim_a_id == id_a,
                        Contradiction.claim_b_id == id_b,
                        Contradiction.status == 'open',
                        Contradiction.detected_at >= datetime.now(timezone.utc) - timedelta(days=cfg.regression_dedup_days)
                    ).first()

                    if not recent_open:
                        # --- Severity + cost via per-org service ---
                        sev_result = calculate_severity_and_cost(
                            org_id=org_id,
                            canonical_entity=new_claim.entity_hint,
                            nli_confidence=result["confidence"],
                            db=db,
                        )

                        # REG-04: Store actual cosine similarity, not 0.85
                        cosine_similarity = float(1.0 - distance)

                        contra = Contradiction(
                            org_id=org_id,
                            claim_a_id=id_a,
                            claim_b_id=id_b,
                            cosine_similarity=cosine_similarity,
                            nli_score=result["confidence"],
                            severity=sev_result.severity,
                            cost_usd=sev_result.cost_usd,
                            status="open",
                        )

                        try:
                            with db.begin_nested():
                                db.add(contra)
                                db.flush()
                            contradiction_ids.append(str(contra.id))
                            logger.info(
                                f"⚡ Contradiction logged: entity='{new_claim.entity_hint}' "
                                f"severity={sev_result.severity} cost=${sev_result.cost_usd} "
                                f"nli={result['confidence']:.2f}"
                            )
                        except (IntegrityError, OperationalError):
                            logger.warning(
                                f"Concurrent insert collision avoided for pair {id_a}-{id_b}. Handled safely."
                            )

        db.commit()
        return contradiction_ids

    except Exception as e:
        db.rollback()
        logger.error(f"Detection funnel failed: {e}")
        raise
    finally:
        db.close()