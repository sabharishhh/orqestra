import os
import logging
import dspy
import numpy as np
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from core.database import SessionLocal
from models.database import Claim, Contradiction, EntityBeliefState

logger = logging.getLogger(__name__)

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
# LEVEL 4: THE HEAVYWEIGHT DEBERTA BOUNCER
# ==========================================
class LocalBouncerContainer:
    """Lazily allocates machine resources for local cross-encoder classification."""
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._tokenizer = None
        self._model = None
        self._torch = None

    def _load(self):
        if self._model is not None:
            return
        
        logger.info(f"📥 Loading Heavyweight DeBERTa model ({self.model_name}) onto memory tier...")
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            
            if hasattr(self._torch.backends, 'mps') and self._torch.backends.mps.is_available():
                self._model = self._model.to("mps")
                logger.info("⚡ Apple Silicon MPS accelerator found. Heavyweight Bouncer bound to MPS context.")
            elif self._torch.cuda.is_available():
                self._model = self._model.to("cuda")
                logger.info("⚡ CUDA accelerator found. Heavyweight Bouncer bound to CUDA context.")
            else:
                logger.info("🛡️ No accelerator found. Bouncer running on local CPU thread context.")
                
        except ImportError as env_err:
            logger.error(f"❌ Missing critical processing dependencies: {env_err}")
            raise env_err

    def evaluate_pair(self, text_a: str, text_b: str) -> dict:
        self._load()
        inputs = self._tokenizer(text_a, text_b, padding=True, truncation=True, max_length=512, return_tensors="pt")
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with self._torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits[0]
            probabilities = self._torch.softmax(logits, dim=0).tolist()

        id2label = self._model.config.id2label
        id_mapping = {int(k): str(v).upper() for k, v in id2label.items()}
        if not any(k in ["CONTRADICTION", "ENTAILMENT", "NEUTRAL"] for k in id_mapping.values()):
            id_mapping = {0: "CONTRADICTION", 1: "ENTAILMENT", 2: "NEUTRAL"}

        max_idx = probabilities.index(max(probabilities))
        return {
            "prediction": id_mapping.get(max_idx, "UNKNOWN"),
            "confidence": probabilities[max_idx]
        }

bouncer = LocalBouncerContainer(model_name="MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli")


# ==========================================
# BUSINESS LOGIC & FUNNEL
# ==========================================
def calculate_severity(entity: str, score: float) -> str:
    normalized = entity.lower().strip()
    critical_domains = ["compliance", "legal", "pricing", "clinical"]
    high_domains = ["policy", "product", "consumer", "weekly schedule", "monthly food selection", "workout routine exercises"]
    
    if score >= 0.85:
        if normalized in critical_domains: return "critical"
        if normalized in high_domains: return "high"
        return "medium"
    elif score >= 0.70:
        if normalized in critical_domains: return "high"
        return "medium"
    return "low"


def is_concurrent(clock_a: dict, clock_b: dict) -> bool:
    """LEVEL 1 MATH: Determines if two vector clocks are strictly concurrent using the Disjoint Set Rule."""
    if not clock_a or not clock_b:
        return True
    if clock_a == clock_b:
        return False # ISSUE-12: equal clocks represent identical logical state, not concurrency
    if not set(clock_a.keys()).intersection(set(clock_b.keys())):
        return True
        
    a_leq_b = True
    b_leq_a = True
    all_keys = set(clock_a.keys()).union(set(clock_b.keys()))
    
    for k in all_keys:
        val_a = clock_a.get(k, 0)
        val_b = clock_b.get(k, 0)
        if val_a > val_b: a_leq_b = False
        if val_b > val_a: b_leq_a = False
            
    return not (a_leq_b or b_leq_a)


def has_active_semantic_conflict(db: Session, new_claim_embedding: list, entity_hint: str) -> bool:
    """F2.5 Compliance: Smart Semantic Cluster Suppression."""
    open_contras = db.query(Contradiction).join(
        Claim, Contradiction.claim_a_id == Claim.id
    ).filter(
        Claim.entity_hint == entity_hint,
        Contradiction.status == 'open'
    ).all()
    
    for c in open_contras:
        claim_a = db.query(Claim).filter(Claim.id == c.claim_a_id).first()
        if claim_a and claim_a.embedding is not None and len(claim_a.embedding) > 0:
            if calculate_cosine_distance(new_claim_embedding, claim_a.embedding) <= 0.05:
                return True
    return False


def run_5_level_funnel(system_id: str, updated_entities: list) -> list:
    """Worker 4 Phase: Implements the complete 5-Level Detection Funnel in Strict Order."""
    if not updated_entities:
        return []
        
    db: Session = SessionLocal()
    contradiction_ids = []
    
    try:
        new_claims = db.query(Claim).filter(
            Claim.system_id == system_id,
            Claim.entity_hint.in_(updated_entities)
        ).all()
        
        for new_claim in new_claims:
            
            # --- F1.1 BOOTSTRAP GATE ---
            # Spec: when claim_count < 3, skip Levels 0 & 1 (OBG centroid + vector clock)
            # and run from Level 3. Do NOT skip detection entirely.
            sys_obg = db.query(EntityBeliefState).filter_by(
                system_id=system_id, 
                entity_name=new_claim.entity_hint
            ).first()
            
            is_bootstrapping = not sys_obg or sys_obg.sample_count < 3
            
            # Candidate pool for Level 3 — all historical claims from other systems for this entity
            all_other_claims = db.query(Claim).filter(
                Claim.system_id != system_id,
                Claim.entity_hint == new_claim.entity_hint
            ).all()
            
            if not all_other_claims:
                logger.info(f"No cross-system claims for '{new_claim.entity_hint}'. Skipping.")
                continue
            
            if is_bootstrapping:
                # F1.1: Skip Levels 0 & 1, run from Level 3 directly
                logger.info(f"F1.1 Bootstrap: '{new_claim.entity_hint}' < 3 samples for system {system_id}. Bypassing Levels 0 & 1, entering at Level 3.")
                level3_candidates = all_other_claims
            else:
                # --- LEVEL 0: OBG CENTROID VARIANCE ---
                other_obgs = db.query(EntityBeliefState).filter(
                    EntityBeliefState.entity_name == new_claim.entity_hint,
                    EntityBeliefState.system_id != system_id
                ).all()
                
                if other_obgs:
                    diverges = False
                    for obg in other_obgs:
                        if obg.sample_count < 3:
                            continue
                        dist = calculate_cosine_distance(new_claim.embedding, obg.centroid_embedding)
                        if dist > 0.35:
                            diverges = True
                            break
                            
                    if not diverges:
                        logger.info(f"LEVEL 0: Claim does not diverge (>0.35) from any other system's OBG for '{new_claim.entity_hint}'. Dropped.")
                        continue

                # --- LEVEL 1: VECTOR CLOCK CAUSALITY ---
                concurrent_claims = []
                for hist in all_other_claims:
                    if is_concurrent(new_claim.vector_clock, hist.vector_clock):
                        concurrent_claims.append(hist)
                    else:
                        logger.info(f"LEVEL 1: Chronological update detected for '{new_claim.entity_hint}'. Dropped.")
                        
                if not concurrent_claims:
                    continue
                
                level3_candidates = concurrent_claims

            # --- LEVEL 3: HNSW VECTOR SEARCH ---
            close_neighbors = []
            for neighbor in level3_candidates:
                dist = calculate_cosine_distance(new_claim.embedding, neighbor.embedding)
                if dist <= 0.40:
                    close_neighbors.append((neighbor, dist))
            
            for neighbor, distance in close_neighbors:
                
                # --- F2.5 Semantic Cluster Suppression ---
                if has_active_semantic_conflict(db, new_claim.embedding, new_claim.entity_hint):
                    logger.info(f"🛡️ Alert Suppressed: Semantic cluster for '{new_claim.entity_hint}' already has an active ticket.")
                    continue
                
                claim_a_str = f"{new_claim.subject} {new_claim.predicate} {new_claim.object}"
                claim_b_str = f"{neighbor.subject} {neighbor.predicate} {neighbor.object}"
                
                # --- LEVEL 4: Local Neuro-Symbolic NLI (DeBERTa) ---
                result = bouncer.evaluate_pair(claim_a_str, claim_b_str)
                
                if result["prediction"] == "CONTRADICTION" and result["confidence"] >= 0.70:
                    
                    # --- LEVEL 5: THE DSPY APEX JUDGE ---
                    try:
                        apex_res = apex_judge(claim_a=claim_a_str, claim_b=claim_b_str, topic=new_claim.entity_hint)
                        if "true" not in str(apex_res.is_contradiction).lower():
                            logger.info(f"⚖️ Apex Judge Override: DeBERTa flagged '{new_claim.entity_hint}', but DSPy found conditional compatibility. Alert dropped.")
                            continue
                    except Exception as apex_err:
                        logger.error(f"Apex Judge failed, falling back to DeBERTa verdict: {apex_err}")
                    
                    id_a, id_b = sorted([str(new_claim.id), str(neighbor.id)])
                    
                    # --- REG-05: Time-bounded regression dedup logic ---
                    recent_open = db.query(Contradiction).filter(
                        Contradiction.claim_a_id == id_a,
                        Contradiction.claim_b_id == id_b,
                        Contradiction.status == 'open',
                        Contradiction.detected_at >= datetime.now(timezone.utc) - timedelta(days=7)
                    ).first()
                    
                    if not recent_open:
                        severity = calculate_severity(new_claim.entity_hint, result["confidence"])
                        
                        # REG-04: Store actual cosine similarity instead of 0.85
                        cosine_similarity = float(1.0 - distance)
                        
                        contra = Contradiction(
                            claim_a_id=id_a,
                            claim_b_id=id_b,
                            cosine_similarity=cosine_similarity, 
                            nli_score=result["confidence"],
                            severity=severity,
                            status="open" 
                        )
                        
                        try:
                            with db.begin_nested():
                                db.add(contra)
                                db.flush()
                            contradiction_ids.append(str(contra.id))
                        except (IntegrityError, OperationalError):
                            logger.warning(f"Concurrent insert collision avoided for pair {id_a}-{id_b}. Handled safely.")
                            
        db.commit()
        return contradiction_ids
        
    except Exception as e:
        db.rollback()
        logger.error(f"Detection funnel failed: {e}")
        raise
    finally:
        db.close()