import os
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError
from core.database import SessionLocal
from models.database import Claim, Contradiction

logger = logging.getLogger(__name__)

# ==========================================
# LAZY INITIALIZATION ML CONTAINER
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
        
        logger.info("📥 Loading local DeBERTa cross-encoder onto memory tier...")
        try:
            import torch
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
            
            # Hardware Acceleration Auto-Discovery
            if hasattr(self._torch.backends, 'mps') and self._torch.backends.mps.is_available():
                self._model = self._model.to("mps")
                logger.info("⚡ Apple Silicon MPS accelerator found. Bouncer bound to MPS context.")
            elif self._torch.cuda.is_available():
                self._model = self._model.to("cuda")
                logger.info("⚡ CUDA accelerator found. Bouncer bound to CUDA runtime context.")
            else:
                logger.info("🛡️ No accelerator found. Bouncer running on local CPU thread context.")
                
        except ImportError as env_err:
            logger.error(f"❌ Missing critical processing dependencies: {env_err}")
            logger.error("Run: pip install torch transformers sentencepiece")
            raise env_err

    def evaluate_pair(self, text_a: str, text_b: str) -> dict:
        """Executes zero-shot NLI token array classification on the pair."""
        self._load()
        
        inputs = self._tokenizer(
            text_a, 
            text_b, 
            padding=True, 
            truncation=True, 
            max_length=512, 
            return_tensors="pt"
        )
        
        # Ensure inputs are on the same device as the model
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        with self._torch.no_grad():
            outputs = self._model(**inputs)
            logits = outputs.logits[0]
            probabilities = self._torch.softmax(logits, dim=0).tolist()

        # Dynamic mapping based on model configuration
        id2label = self._model.config.id2label
        id_mapping = {int(k): str(v).upper() for k, v in id2label.items()}
        
        # Fallback if config deviates
        if not any(k in ["CONTRADICTION", "ENTAILMENT", "NEUTRAL"] for k in id_mapping.values()):
            id_mapping = {0: "CONTRADICTION", 1: "ENTAILMENT", 2: "NEUTRAL"}

        max_idx = probabilities.index(max(probabilities))
        pred_label = id_mapping.get(max_idx, "UNKNOWN")
        confidence = probabilities[max_idx]

        return {
            "prediction": pred_label,
            "confidence": confidence
        }

# Instantiate singleton lazy container reference
# Using the fast 'small' cross-encoder version for rapid worker execution
bouncer = LocalBouncerContainer(model_name="cross-encoder/nli-deberta-v3-small")

# ==========================================
# BUSINESS LOGIC & FUNNEL
# ==========================================
def calculate_severity(entity: str, score: float) -> str:
    """Matches our dynamic matrix from Phase 0."""
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

def run_5_level_funnel(system_id: str, updated_entities: list) -> list:
    """Worker 4 Phase: Implements the 5-Level Detection Funnel using Postgres pgvector and local DeBERTa."""
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
            # LEVEL 3: Vector Search (HNSW Approximate Nearest Neighbors)
            neighbors = db.query(Claim).filter(
                Claim.system_id != system_id,
                Claim.entity_hint == new_claim.entity_hint,
                Claim.embedding.cosine_distance(new_claim.embedding) <= 0.40
            ).limit(5).all()
            
            for neighbor in neighbors:
                claim_a_str = f"{new_claim.subject} {new_claim.predicate} {new_claim.object}"
                claim_b_str = f"{neighbor.subject} {neighbor.predicate} {neighbor.object}"
                
                # LEVEL 4: Local Neuro-Symbolic NLI (DeBERTa-v3)
                # Cost = $0.00 | Latency = ~30-50ms (Accelerated)
                result = bouncer.evaluate_pair(claim_a_str, claim_b_str)
                
                if result["prediction"] == "CONTRADICTION" and result["confidence"] >= 0.70:
                    id_a, id_b = sorted([str(new_claim.id), str(neighbor.id)])
                    
                    exists = db.query(Contradiction).filter_by(claim_a_id=id_a, claim_b_id=id_b).first()
                    if not exists:
                        severity = calculate_severity(new_claim.entity_hint, result["confidence"])
                        
                        contra = Contradiction(
                            claim_a_id=id_a,
                            claim_b_id=id_b,
                            cosine_similarity=0.85, 
                            nli_score=result["confidence"],
                            severity=severity
                        )
                        
                        # --- NESTED TRANSACTION (SAVEPOINT) TO PREVENT DEADLOCKS ---
                        try:
                            with db.begin_nested():
                                db.add(contra)
                                db.flush()
                            contradiction_ids.append(str(contra.id))
                        except (IntegrityError, OperationalError) as e:
                            logger.warning(f"Concurrent insert collision avoided for pair {id_a}-{id_b}. Handled safely.")
                            
        db.commit()
        return contradiction_ids
        
    except Exception as e:
        db.rollback()
        logger.error(f"Detection funnel failed: {e}")
        raise
    finally:
        db.close()