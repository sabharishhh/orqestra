"""
Thin async client for GET /canon/resolve.

Used inside LangGraph nodes to fetch declared canonical values pre-answer.
Soft-fails: transport/timeout/4xx errors are logged and returned as
resolution_status='error' — the graph does not raise. Callers get partial
canon and continue.

Fail-null semantics of /canon/resolve are preserved:
  resolution_status='declared'      → value present
  resolution_status='no_declaration' → no human has declared this yet
  resolution_status='error'         → transport/HTTP error (client-side)
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

import httpx

from observability import get_logger

logger = get_logger(__name__)

DEFAULT_TIMEOUT_SECONDS = 5.0


async def resolve_one(
    *,
    entity: str,
    api_base: str,
    api_token: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    """
    Resolve a single canonical entity. Never raises.

    Returns a dict of shape:
        {
          "entity_requested": <entity>,
          "entity_resolved":  <canonical name or entity_requested on error>,
          "canonical_value":  <str | None>,
          "canonical_claim_text": <str | None>,
          "resolution_status": "declared" | "no_declaration" | "error",
          "resolved_from_store_id": <str | None>,
          "declared_by": <str | None>,
          "declared_at": <str | None>,
          "error": <str | None>,   # only present on error
        }
    """
    url = f"{api_base.rstrip('/')}/canon/resolve"
    headers = {"Authorization": f"Bearer {api_token}"}
    params = {"entity": entity}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as e:
        logger.warning("canon_client.transport_error", entity=entity, error=str(e))
        return _error_shape(entity, f"transport: {e!s}")

    if r.status_code != 200:
        logger.warning(
            "canon_client.non_200",
            entity=entity,
            status_code=r.status_code,
            body_preview=r.text[:200],
        )
        return _error_shape(entity, f"http {r.status_code}")

    try:
        body = r.json()
    except Exception as e:
        logger.warning("canon_client.bad_json", entity=entity, error=str(e))
        return _error_shape(entity, f"bad_json: {e!s}")

    # Normalize: /resolve already returns the right shape; we just add error=None.
    body.setdefault("error", None)
    return body


async def resolve_many(
    *,
    entities: list[str],
    api_base: str,
    api_token: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, dict]:
    """
    Resolve a list of entities sequentially. Returns {entity: resolve_dict}.
    Sequential (not concurrent) for Sprint 9 — keeps latency predictable
    and preserves clear log ordering. Concurrent variant is trivial to
    add later if a fleet of entities per agent grows past ~5.
    """
    results: dict[str, dict] = {}
    for e in entities:
        results[e] = await resolve_one(
            entity=e, api_base=api_base, api_token=api_token, timeout=timeout
        )
    return results


def _error_shape(entity: str, err: str) -> dict:
    return {
        "entity_requested": entity,
        "entity_resolved": entity,
        "canonical_value": None,
        "canonical_claim_text": None,
        "resolution_status": "error",
        "resolved_from_store_id": None,
        "declared_by": None,
        "declared_at": None,
        "error": err,
    }