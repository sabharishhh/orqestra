"""Structured logging configuration for Orqestra.

Single chokepoint for log setup. JSON in prod, pretty-printed in dev.
Controlled by ORQESTRA_ENV env var (values: "dev", "prod"). Defaults to "dev".
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor

_CONFIGURED = False


def _drop_color_message_key(
    _logger: Any, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Uvicorn duplicates the event message with ANSI codes under `color_message`. Strip it."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging() -> None:
    """Configure structlog and the stdlib logging module.

    Idempotent: subsequent calls are no-ops. Call once at process startup
    (FastAPI app factory and Celery worker init).
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    env = os.getenv("ORQESTRA_ENV", "dev").lower()
    is_prod = env == "prod"
    log_level_name = os.getenv("ORQESTRA_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _drop_color_message_key,
    ]

    if is_prod:
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=shared_processors
        + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(log_level)

    # Quiet known-noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger. Pass `__name__` from the calling module."""
    return structlog.get_logger(name)