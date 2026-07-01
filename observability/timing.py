"""Timing instrumentation primitive.

Single context manager that emits a structured log event with duration_ms,
and also feeds the Prometheus registry when ORQESTRA_METRICS_ENABLED=true.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator

from observability import metrics
from observability.logging import get_logger

_logger = get_logger("observability.timed")


@contextmanager
def timed(event: str, **fields: Any) -> Iterator[dict]:
    """Time a block and emit `event` with duration_ms + any fields."""
    ctx: dict[str, Any] = {}
    start = time.perf_counter()
    try:
        yield ctx
    finally:
        duration_s = time.perf_counter() - start
        duration_ms = round(duration_s * 1000, 2)
        _logger.info(event, duration_ms=duration_ms, **fields, **ctx)

        # Feed Prometheus where applicable
        if event == "db.query":
            qn = fields.get("query_name") or ctx.get("query_name")
            if qn:
                metrics.observe_db_query(qn, duration_s)
        elif event == "detection.level.completed":
            lvl = fields.get("funnel_level")
            outcome = ctx.get("outcome")
            if lvl is not None:
                metrics.observe_detection_level(lvl, outcome, duration_s)