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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _ensure_demo_org_seeded() -> None:
    """Idempotent boot-time seed of the demo-fitness organization."""
    try:
        from core.database import SessionLocal
        from models.database import Organization, DetectionConfig
        from scripts.seed_org import seed
    except Exception as e:
        logger.warning(f"Auto-seed skipped — import failed: {e}")
        return

    db = SessionLocal()
    try:
        org = db.query(Organization).filter_by(slug="demo-fitness").first()
        has_config = False
        if org is not None:
            has_config = db.query(DetectionConfig).filter_by(org_id=org.id).first() is not None

        if org and has_config:
            logger.info(f"Auto-seed: demo-fitness already seeded (org_id={org.id}). Skipping.")
            return

        logger.info("Auto-seed: demo-fitness incomplete — running seed against presets/consumer.yaml")
        org_id = seed(
            name="Demo Fitness",
            slug="demo-fitness",
            preset_name="consumer",
            description="Seeded automatically on API startup",
        )
        logger.info(f"Auto-seed: complete (org_id={org_id})")
    except Exception as e:
        logger.error(f"Auto-seed FAILED (non-fatal — defaults will be used): {e}")
    finally:
        db.close()


@app.on_event("startup")
async def on_startup():
    _ensure_demo_org_seeded()


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