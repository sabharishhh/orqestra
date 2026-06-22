import os
from celery import Celery

# Redis is the standard, high-performance broker for Celery queues
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "orqestra_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["workers.tasks"]
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
    worker_prefetch_multiplier=1
)