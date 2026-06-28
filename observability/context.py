"""Context variables for request-scoped logging fields.

These ContextVars are merged into every structlog event by
`structlog.contextvars.merge_contextvars` (already wired in observability/logging.py).
"""

from __future__ import annotations

import contextvars
from typing import Optional

import structlog

request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)
tenant_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "tenant_id", default=None
)
org_slug_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "org_slug", default=None
)
claim_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "claim_id", default=None
)


def bind_tenant(tenant_id: str, org_slug: str) -> None:
    """Bind tenant context. Call after the org has been resolved on a request."""
    tenant_id_ctx.set(tenant_id)
    org_slug_ctx.set(org_slug)
    structlog.contextvars.bind_contextvars(tenant_id=tenant_id, org_slug=org_slug)


def bind_claim(claim_id: str) -> None:
    """Bind claim context. Call at the top of a claim-processing Celery task."""
    claim_id_ctx.set(claim_id)
    structlog.contextvars.bind_contextvars(claim_id=claim_id)


def clear_tenant() -> None:
    tenant_id_ctx.set(None)
    org_slug_ctx.set(None)
    structlog.contextvars.unbind_contextvars("tenant_id", "org_slug")


def clear_claim() -> None:
    claim_id_ctx.set(None)
    structlog.contextvars.unbind_contextvars("claim_id")