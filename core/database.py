import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


SQLALCHEMY_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/orqestra",
)

# Pool sizing (Sprint 11 Task 2b): the demo fleet does 5 agents × ~7 canon
# lookups × in parallel, plus concurrent sample POSTs and Celery workers.
# Defaults (5/10) starve the fleet — see logs 2026-07-02 QueuePool timeout.
# Env-overridable for prod tuning without a rebuild.
POOL_SIZE = int(os.environ.get("ORQESTRA_DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.environ.get("ORQESTRA_DB_MAX_OVERFLOW", "40"))
POOL_TIMEOUT = int(os.environ.get("ORQESTRA_DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.environ.get("ORQESTRA_DB_POOL_RECYCLE", "1800"))

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    pool_pre_ping=True,  # drop stale connections silently
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()