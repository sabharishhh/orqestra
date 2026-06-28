import os
from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging
from kombu import Queue

from observability import configure_logging

configure_logging()
import observability.celery_signals


@setup_logging.connect
def _disable_celery_logging_override(**kwargs):
    """Prevent Celery from clobbering our structlog config."""
    pass


# Redis is the standard, high-performance broker for Celery queues
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "orqestra_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    # FIX: Explicitly include all tasks to prevent "unregistered task" crash
    include=[
        "workers.tasks",
        "workers.feedback_collector",
        "workers.auto_induction",
        "workers.coherence_scorer",
        "workers.canary_injector",
    ],
)

# FIX: Explicitly define the queues so DLQ is actually created in Redis
celery_app.conf.task_queues = (
    Queue("celery"),
    Queue("claim_extraction"),
    Queue("dead_letters"),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # F5.2 Guardrail: Ensure tasks don't silently fail and break the chain
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        # FIX: The exact task name instead of the broken glob pattern
        "workers.tasks.dlq_handler": {"queue": "dead_letters"},
    },
)

# WIRING: Celery Beat Schedule for background daemons
celery_app.conf.beat_schedule = {
    "nightly-ontology-induction": {
        "task": "workers.auto_induction.run_nightly_induction",
        "schedule": crontab(hour=2, minute=0),  # Runs at 2:00 AM UTC
    },
    "hourly-coherence-score": {
        "task": "workers.tasks.trigger_all_coherence_scores",
        "schedule": crontab(minute=0),  # Runs at the top of every hour
    },
    "hourly-canary-check": {
        "task": "workers.canary_injector.run_canary_check",
        "schedule": crontab(minute=15),  # 15 min past every hour
    },
}