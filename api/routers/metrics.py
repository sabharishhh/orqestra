"""GET /metrics — Prometheus exposition endpoint.

Returns 404 when ORQESTRA_METRICS_ENABLED is not 'true' so we don't expose
an empty endpoint in environments where metrics aren't expected.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from observability import metrics

router = APIRouter()


@router.get("/metrics")
def get_metrics():
    if not metrics.ENABLED:
        raise HTTPException(status_code=404, detail="Metrics disabled.")
    body, content_type = metrics.render()
    return Response(content=body, media_type=content_type)