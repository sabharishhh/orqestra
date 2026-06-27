import logging
from celery import chain
from core.celery_app import celery_app

from services.pii_scrubber import scrub_pii
from workers.claim_extractor import run_extraction
from workers.sccg_writer import write_claims_to_sccg
from workers.obg_updater import update_entity_centroids
from workers.contradiction_detector import run_5_level_funnel
from workers.resolution_agent import generate_resolution
from workers.alert_dispatcher import send_slack_alert

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def process_sample_task(
    self,
    system_id: str,
    text: str,
    metadata: dict = None,
    parent_claim_id: str = None,
):
    """Master entry point. PII-scrubs, then chains the pipeline."""
    logger.info(
        f"Initiating pipeline for System [{system_id}]"
        + (f" with parent_claim_id={parent_claim_id}" if parent_claim_id else "")
    )

    from core.database import SessionLocal
    from models.database import System
    db = SessionLocal()
    try:
        sys_row = db.query(System.org_id).filter(System.id == system_id).first()
        org_id_for_scrub = str(sys_row.org_id) if sys_row and sys_row.org_id else None
    finally:
        db.close()

    safe_text = scrub_pii(text, org_id=org_id_for_scrub)

    workflow = chain(
        extract_and_embed_task.s(system_id, safe_text, metadata or {}, parent_claim_id),
        write_sccg_task.s(system_id, parent_claim_id),
        update_obg_task.s(system_id),
        detect_contradictions_task.s(system_id),
    )
    workflow.apply_async()
    return {"status": "workflow_chained"}


@celery_app.task(bind=True, max_retries=3, queue='claim_extraction')
def extract_and_embed_task(self, system_id: str, text: str, metadata: dict, parent_claim_id: str = None):
    """Worker 1: extract SPO claims + embeddings via OpenAI."""
    embedded = run_extraction(text, system_id)
    return {"claims": embedded, "parent_claim_id": parent_claim_id, "metadata": metadata or {}}


@celery_app.task(bind=True, max_retries=3)
def write_sccg_task(self, prev_result: dict, system_id: str, parent_claim_id: str = None):
    """Worker 2: persist claims to SCCG with optional cross-agent parent linkage."""
    if not isinstance(prev_result, dict):
        logger.warning(f"write_sccg_task got non-dict prev_result: {type(prev_result)}")
        return []
    claims = prev_result.get("claims", [])
    # Prefer explicit kwarg, fall back to value tunneled from extract step
    effective_parent = parent_claim_id or prev_result.get("parent_claim_id")
    return write_claims_to_sccg(system_id, claims, parent_claim_id=effective_parent)


@celery_app.task(bind=True)
def update_obg_task(self, claim_ids: list, system_id: str):
    """Worker 3: Update OBG centroids."""
    return update_entity_centroids(system_id, claim_ids)


@celery_app.task(bind=True)
def detect_contradictions_task(self, updated_entities: list, system_id: str):
    """Worker 4: 5-Level Funnel."""
    contradiction_ids = run_5_level_funnel(system_id, updated_entities)
    for cid in contradiction_ids:
        resolve_contradiction_task.delay(cid)
    return {"contradictions_found": len(contradiction_ids)}


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def resolve_contradiction_task(self, contradiction_id: str):
    """Worker 5: Explainer agent."""
    try:
        generate_resolution(contradiction_id)
        return {"status": "resolved", "id": contradiction_id}
    except Exception as exc:
        logger.error(f"Resolution failed: {exc}. Routing to DLQ.")
        dlq_handler.apply_async(args=[{"contradiction_id": contradiction_id}, str(exc)], queue='dead_letters')
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3)
def dispatch_alert_task(self, resolution_id: str):
    send_slack_alert(resolution_id)
    return {"status": "alert_dispatched", "resolution_id": resolution_id}


@celery_app.task(queue='dead_letters')
def dlq_handler(failed_payload: dict, error_msg: str):
    logger.critical(f"DLQ CAUGHT: {error_msg} | Payload: {failed_payload}")
    return {"status": "dead_letter_logged"}


@celery_app.task
def trigger_all_coherence_scores():
    from core.database import SessionLocal
    from models.database import System
    from workers.coherence_scorer import update_coherence_score
    db = SessionLocal()
    try:
        systems = db.query(System).all()
        for sys in systems:
            update_coherence_score.delay(str(sys.id))
    finally:
        db.close()


@celery_app.task
def trigger_finetune_task(entity_type: str):
    logger.info(f"🚀 REINFORCEMENT LEARNING KICKOFF: Fine-tuning DeBERTa for domain: {entity_type}")
    return {"status": "finetune_started", "domain": entity_type}