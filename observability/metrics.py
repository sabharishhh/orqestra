"""Prometheus metrics registry — opt-in via ORQESTRA_METRICS_ENABLED.

When disabled (default), every helper is a no-op and prometheus_client
is not even instantiated. When enabled, a single CollectorRegistry holds
all Orqestra histograms/counters and is exposed via GET /metrics.

Bucket boundaries chosen to span sub-millisecond DB lookups through
multi-second LLM calls.
"""

from __future__ import annotations

import os
from typing import Optional

ENABLED = os.environ.get("ORQESTRA_METRICS_ENABLED", "false").lower() == "true"

_registry = None
_http_request_duration = None
_db_query_duration = None
_llm_call_duration = None
_llm_tokens_total = None
_embedding_call_duration = None
_embedding_tokens_total = None
_detection_level_duration = None
_celery_task_duration = None

# Histogram buckets in seconds. Spans 5ms → 10s.
_DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def _init() -> None:
    global _registry, _http_request_duration, _db_query_duration
    global _llm_call_duration, _llm_tokens_total
    global _embedding_call_duration, _embedding_tokens_total
    global _detection_level_duration, _celery_task_duration

    if _registry is not None:
        return  # idempotent

    from prometheus_client import CollectorRegistry, Counter, Histogram

    _registry = CollectorRegistry()

    _http_request_duration = Histogram(
        "orqestra_http_request_duration_seconds",
        "HTTP request duration in seconds.",
        labelnames=("method", "path", "status"),
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )
    _db_query_duration = Histogram(
        "orqestra_db_query_duration_seconds",
        "Database query duration in seconds.",
        labelnames=("query_name",),
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )
    _llm_call_duration = Histogram(
        "orqestra_llm_call_duration_seconds",
        "LLM call duration in seconds.",
        labelnames=("purpose",),
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )
    _llm_tokens_total = Counter(
        "orqestra_llm_tokens_total",
        "Total tokens consumed by LLM calls.",
        labelnames=("purpose", "direction"),
        registry=_registry,
    )
    _embedding_call_duration = Histogram(
        "orqestra_embedding_call_duration_seconds",
        "Embedding call duration in seconds.",
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )
    _embedding_tokens_total = Counter(
        "orqestra_embedding_tokens_total",
        "Total tokens consumed by embedding calls.",
        registry=_registry,
    )
    _detection_level_duration = Histogram(
        "orqestra_detection_level_duration_seconds",
        "Detection funnel level duration in seconds.",
        labelnames=("funnel_level", "outcome"),
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )
    _celery_task_duration = Histogram(
        "orqestra_celery_task_duration_seconds",
        "Celery task duration in seconds.",
        labelnames=("task_name", "state"),
        buckets=_DURATION_BUCKETS,
        registry=_registry,
    )


if ENABLED:
    _init()


# =====================================================
# Public observation helpers — no-op when disabled
# =====================================================

def observe_http_request(method: str, path: str, status: int, duration_s: float) -> None:
    if ENABLED:
        _http_request_duration.labels(method=method, path=path, status=str(status)).observe(duration_s)


def observe_db_query(query_name: str, duration_s: float) -> None:
    if ENABLED:
        _db_query_duration.labels(query_name=query_name).observe(duration_s)


def observe_llm_call(purpose: str, input_tokens: int, output_tokens: int, duration_s: float) -> None:
    if ENABLED:
        _llm_call_duration.labels(purpose=purpose).observe(duration_s)
        _llm_tokens_total.labels(purpose=purpose, direction="input").inc(input_tokens)
        _llm_tokens_total.labels(purpose=purpose, direction="output").inc(output_tokens)


def observe_embedding_call(input_tokens: int, duration_s: float) -> None:
    if ENABLED:
        _embedding_call_duration.observe(duration_s)
        _embedding_tokens_total.inc(input_tokens)


def observe_detection_level(funnel_level: int, outcome: Optional[str], duration_s: float) -> None:
    if ENABLED:
        _detection_level_duration.labels(
            funnel_level=str(funnel_level),
            outcome=outcome or "unknown",
        ).observe(duration_s)


def observe_celery_task(task_name: str, state: Optional[str], duration_s: float) -> None:
    if ENABLED:
        _celery_task_duration.labels(
            task_name=task_name,
            state=state or "unknown",
        ).observe(duration_s)


def render() -> tuple[bytes, str]:
    """Return (body, content_type) for the /metrics endpoint."""
    if not ENABLED or _registry is None:
        return b"", "text/plain; version=0.0.4; charset=utf-8"
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    return generate_latest(_registry), CONTENT_TYPE_LATEST