import re
import logging
from celery import chain
from core.celery_app import celery_app

# Import our worker logic modules
from workers.claim_extractor import run_extraction
from workers.sccg_writer import write_claims_to_sccg
from workers.obg_updater import update_entity_centroids
from workers.contradiction_detector import run_5_level_funnel
from workers.resolution_agent import generate_resolution
from workers.alert_dispatcher import send_slack_alert

logger = logging.getLogger(__name__)

def scrub_pii(text: str) -> str:
    """F5.1 Compliance: Strip PHI/PII before it hits the DB or Embedder."""
    if not text:
        return ""
    # Scrub SSNs
    text = re.sub(r'\b\d{3}-\d{2}-\d{4}\b', '[REDACTED_SSN]', text)
    # Scrub Emails
    text = re.sub(r'\b[\w\.-]+@[\w\.-]+\.\w{2,4}\b', '[REDACTED_EMAIL]', text)
    # Scrub Phone Numbers
    text = re.sub(r'\b\d{3}[-.\s]??\d{3}[-.\s]??\d{4}\b', '[REDACTED_PHONE]', text)
    # Scrub Medical Record Numbers (Mock Format)
    text = re.sub(r'\b[A-Z]{2,3}-\d{6,8}\b', '[REDACTED_MRN]', text)
    return text

@celery_app.task(bind=True, max_retries=3)
def process_sample_task(self, system_id: str, text: str, metadata: dict = None):
    """
    The master entry point for the Async Pipeline.
    """
    logger.info(f"Initiating pipeline for System [{system_id}]")

    # F5.1 Guardrail: PII Scrubbing happens instantly before any downstream logic
    safe_text = scrub_pii(text)

    # F5.2 Guardrail: Celery Chain execution
    workflow = chain(
        extract_and_embed_task.s(system_id, safe_text, metadata or {}),
        write_sccg_task.s(system_id),
        update_obg_task.s(system_id),
        detect_contradictions_task.s(system_id)
    )
    
    workflow.apply_async()
    return {"status": "workflow_chained"}


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def extract_and_embed_task(self, system_id: str, text: str, metadata: dict):
    """Worker 1: Extracts SPO triples and embeds them."""
    try:
        embedded_claims = run_extraction(text)
        return embedded_claims 
    except Exception as exc:
        # F5.3 Compliance: Route terminal failures to Dead Letter Queue
        logger.error(f"Extraction failed: {exc}. Routing to DLQ.")
        dlq_handler.apply_async(args=[{"system_id": system_id, "text": text}, str(exc)], queue='dead_letters')
        raise self.retry(exc=exc)


@celery_app.task(bind=True)
def write_sccg_task(self, embedded_claims: list, system_id: str):
    """Worker 2: Commits embedded claims to the Sparse Causal Claim Graph."""
    claim_ids = write_claims_to_sccg(system_id, embedded_claims)
    return claim_ids


@celery_app.task(bind=True)
def update_obg_task(self, claim_ids: list, system_id: str):
    """Worker 3: Updates the running centroids in the Organizational Belief Graph."""
    updated_entities = update_entity_centroids(system_id, claim_ids)
    return updated_entities 


@celery_app.task(bind=True)
def detect_contradictions_task(self, updated_entities: list, system_id: str):
    """Worker 4: Executes the 5-Level Funnel against newly updated entity spaces."""
    contradiction_ids = run_5_level_funnel(system_id, updated_entities)
    
    for cid in contradiction_ids:
        resolve_contradiction_task.delay(cid)
        
    return {"contradictions_found": len(contradiction_ids)}


@celery_app.task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def resolve_contradiction_task(self, contradiction_id: str):
    """Worker 5: The explainer agent."""
    try:
        generate_resolution(contradiction_id)
        return {"status": "resolved", "id": contradiction_id}
    except Exception as exc:
        logger.error(f"Resolution failed: {exc}. Routing to DLQ.")
        dlq_handler.apply_async(args=[{"contradiction_id": contradiction_id}, str(exc)], queue='dead_letters')
        raise self.retry(exc=exc)

@celery_app.task(bind=True, max_retries=3)
def dispatch_alert_task(self, resolution_id: str):
    """Celery wrapper for the Alert Dispatcher."""
    send_slack_alert(resolution_id)
    return {"status": "alert_dispatched", "resolution_id": resolution_id}

@celery_app.task(queue='dead_letters')
def dlq_handler(failed_payload: dict, error_msg: str):
    """F5.3 Compliance: Dead Letter Queue for persistent failures."""
    logger.critical(f"DLQ CAUGHT: {error_msg} | Payload: {failed_payload}")
    return {"status": "dead_letter_logged"}