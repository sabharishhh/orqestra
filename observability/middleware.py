"""Pure ASGI middleware: correlation ID + per-request logging.

Pure ASGI (not BaseHTTPMiddleware) because BaseHTTPMiddleware runs the inner
app in a separate anyio task, which has its own copy of contextvars. Any
context bound inside route handlers or dependencies (e.g. `bind_tenant` in
`verify_api_key`) would be invisible to the outer middleware. Pure ASGI keeps
everything in one task, so contextvars propagate naturally.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from observability.context import request_id_ctx
from observability.logging import get_logger

REQUEST_ID_HEADER = b"x-request-id"

logger = get_logger("observability.request")


class CorrelationIdMiddleware:
    """ASGI middleware that binds a correlation ID and logs request.completed."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        incoming = headers.get(REQUEST_ID_HEADER)
        request_id = incoming.decode() if incoming else uuid.uuid4().hex

        token = request_id_ctx.set(request_id)
        structlog.contextvars.bind_contextvars(request_id=request_id)

        status_holder: dict[str, int] = {"code": 500}

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                response_headers = list(message.get("headers", []))
                response_headers.append((REQUEST_ID_HEADER, request_id.encode()))
                message = {**message, "headers": response_headers}
            await send(message)

        start = time.perf_counter()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path_template = _route_template(scope) or scope.get("path", "")
            logger.info(
                "request.completed",
                method=scope.get("method"),
                path=path_template,
                status_code=status_holder["code"],
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()
            request_id_ctx.reset(token)


def _route_template(scope: dict) -> str | None:
    """Rebuild the parameterized route path from the request's path_params."""
    route = scope.get("route")
    path = scope.get("path", "")
    if route is None:
        return None
    path_params = scope.get("path_params") or {}
    if not path_params:
        return path
    template = path
    for key, value in path_params.items():
        template = template.replace(str(value), "{" + key + "}")
    return template
