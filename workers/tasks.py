import logging
from celery import chain
from core.celery_app import celery_app

# Import our worker logic modules (we will build the internals next)
from workers.claim_extractor import run_extraction
from workers.sccg_writer import write_claims_to_sccg
from workers.obg_updater import update_entity_centroids
from workers.contradiction_detector import run_5_level_funnel
from workers.resolution_agent import generate_resolution
from workers.alert_dispatcher import send_slack_alert

logger = logging.getLogger(__name__)

@celery_app.task(bind=True, max_retries=3)
def process_sample_task(self, system_id: str, text: str, metadata: dict):
    """
    The master entry point for the Async Pipeline.
    Triggered by the FastAPI ingestion endpoints.
    """
    logger.info(f"Initiating pipeline for System [{system_id}]")

    # F5.2 Guardrail: Celery Chain execution
    # This guarantees sequential execution. The output of one task 
    # is automatically passed as the first argument to the next task.
    workflow = chain(
        extract_and_embed_task.s(system_id, text, metadata),
        write_sccg_task.s(system_id),
        update_obg_task.s(system_id),
        detect_contradictions_task.s(system_id)
    )
    
    workflow.apply_async()
    return {"status": "workflow_chained"}


@celery_app.task(bind=True)
def extract_and_embed_task(self, system_id: str, text: str, metadata: dict):
    """Worker 1: Extracts SPO triples via gpt-5.4-mini and embeds them."""
    # Ported from Phase 0 Module 2 & 3
    embedded_claims = run_extraction(text)
    return embedded_claims # Passed to write_sccg_task


@celery_app.task(bind=True)
def write_sccg_task(self, embedded_claims: list, system_id: str):
    """Worker 2: Commits embedded claims to the Sparse Causal Claim Graph."""
    claim_ids = write_claims_to_sccg(system_id, embedded_claims)
    return claim_ids # Passed to update_obg_task


@celery_app.task(bind=True)
def update_obg_task(self, claim_ids: list, system_id: str):
    """Worker 3: Updates the running centroids in the Organizational Belief Graph."""
    updated_entities = update_entity_centroids(system_id, claim_ids)
    return updated_entities # Passed to detect_contradictions_task


@celery_app.task(bind=True)
def detect_contradictions_task(self, updated_entities: list, system_id: str):
    """Worker 4: Executes the 5-Level Funnel against newly updated entity spaces."""
    contradiction_ids = run_5_level_funnel(system_id, updated_entities)
    
    # If contradictions are found, trigger the Resolution Agent asynchronously
    for cid in contradiction_ids:
        resolve_contradiction_task.delay(cid)
        
    return {"contradictions_found": len(contradiction_ids)}


@celery_app.task(bind=True)
def resolve_contradiction_task(self, contradiction_id: str):
    """Worker 5: The gpt-5.4-mini explainer agent."""
    generate_resolution(contradiction_id)
    return {"status": "resolved", "id": contradiction_id}

@celery_app.task(bind=True, max_retries=3)
def dispatch_alert_task(self, resolution_id: str):
    """Celery wrapper for the Alert Dispatcher."""
    send_slack_alert(resolution_id)
    return {"status": "alert_dispatched", "resolution_id": resolution_id}