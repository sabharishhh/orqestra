import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Router Imports
from api.routers import systems, samples, admin, contradictions, entities, graph, resolutions, roi

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Orqestra.API")

app = FastAPI(
    title="Orqestra MVP API",
    version="3.0",
    description="AI Estate Coherence Infrastructure. SCCG + OBG Async Monitoring Layer."
)

# Strict CORS for Dashboard Isolation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update to specific dashboard domains in production
    allow_credentials=True,
    allow_methods=["GET", "POST"], # F8.4 Guardrail: No PUT/DELETE allowed globally
    allow_headers=["*"],
)


# Health Check
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "operational", "engine": "Orqestra v3.0"}

# Mount Routers
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(systems.router, prefix="/systems", tags=["Systems"])
app.include_router(samples.router, prefix="/systems", tags=["Ingestion"])
app.include_router(contradictions.router, prefix="/contradictions", tags=["Contradictions"])
app.include_router(resolutions.router, prefix="/resolutions", tags=["Resolutions"])
app.include_router(entities.router, prefix="/entities", tags=["OBG Entities"])
app.include_router(graph.router, prefix="/graph", tags=["SCCG Visualizer"])
app.include_router(roi.router, prefix="/roi", tags=["Financial ROI"])

logger.info("Orqestra API Core Initialized. Standing by for Swarm Telemetry.")