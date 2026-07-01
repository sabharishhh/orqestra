"""Celery signal hooks: propagate request_id/tenant_id/org_slug into tasks.

On publish (API side): read current contextvars, attach to task headers.
On execution (worker side): read headers, bind to contextvars + structlog.
On completion/failure: log task lifecycle with duration.
"""

from __future__ import annotations

import time

import structlog
from celery.signals import (
    before_task_publish,
    task_failure,
    task_postrun,
    task_prerun,
)

from observability.context import (
    bind_claim,
    bind_tenant,
    claim_id_ctx,
    clear_claim,
    clear_tenant,
    org_slug_ctx,
    request_id_ctx,
    tenant_id_ctx,
)
from observability.logging import get_logger

logger = get_logger("observability.celery")

# Per-task wall clock start, keyed by task_id
_task_start_times: dict[str, float] = {}


@before_task_publish.connect
def inject_context_into_headers(headers=None, **kwargs):
    """API-side: stash current contextvars in task headers."""
    if headers is None:
        return
    rid = request_id_ctx.get()
    tid = tenant_id_ctx.get()
    slug = org_slug_ctx.get()
    cid = claim_id_ctx.get()
    if rid:
        headers["orq_request_id"] = rid
    if tid:
        headers["orq_tenant_id"] = tid
    if slug:
        headers["orq_org_slug"] = slug
    if cid:
        headers["orq_claim_id"] = cid


@task_prerun.connect
def bind_context_from_headers(task_id=None, task=None, **kwargs):
    """Worker-side: pull context from headers and bind to structlog."""
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", None) or {}

    rid = headers.get("orq_request_id")
    tid = headers.get("orq_tenant_id")
    slug = headers.get("orq_org_slug")
    cid = headers.get("orq_claim_id")

    bound = {}
    if rid:
        request_id_ctx.set(rid)
        bound["request_id"] = rid
    if tid and slug:
        bind_tenant(tenant_id=tid, org_slug=slug)
    if cid:
        bind_claim(cid)

    # Also tag task name + id for traceability
    bound["task_name"] = task.name if task else "<unknown>"
    bound["task_id"] = task_id or "<unknown>"
    structlog.contextvars.bind_contextvars(**bound)

    _task_start_times[task_id] = time.perf_counter()
    logger.info("task.started")


@task_postrun.connect
def emit_task_completed(task_id=None, task=None, state=None, **kwargs):
    """Worker-side: emit completion log with duration, clear context."""
    start = _task_start_times.pop(task_id, None)
    duration_ms = round((time.perf_counter() - start) * 1000, 2) if start else None
    logger.info(
        "task.completed",
        state=state,
        duration_ms=duration_ms,
    )
    if duration_ms is not None:
        from observability import metrics
        task_name = task.name if task else "unknown"
        metrics.observe_celery_task(task_name, state, duration_ms / 1000.0)
    structlog.contextvars.clear_contextvars()
    clear_tenant()
    clear_claim()


@task_failure.connect
def emit_task_failed(task_id=None, exception=None, traceback=None, **kwargs):
    """Worker-side: log failures explicitly (task_postrun still fires)."""
    logger.error(
        "task.failed",
        exc_type=type(exception).__name__ if exception else None,
        exc_msg=str(exception) if exception else None,
    )