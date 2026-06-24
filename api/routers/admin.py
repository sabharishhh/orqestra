from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from core.database import get_db

router = APIRouter()

# Simple allowlist to prevent arbitrary SQL injection
ALLOWED_TABLES = ["systems", "entities", "claims", "contradictions", "resolution_proposals", "coherence_scores", "contrastive_feedback"]

@router.get("/table/{table_name}")
def get_table_data(table_name: str, db: Session = Depends(get_db)):
    if table_name not in ALLOWED_TABLES:
        raise HTTPException(status_code=403, detail="Table access forbidden.")
    
    # Raw query to fetch latest 50 rows
    query = text(f"SELECT * FROM {table_name} ORDER BY id LIMIT 50")
    result = db.execute(query)
    
    # Convert to list of dicts
    columns = result.keys()
    return [dict(zip(columns, row)) for row in result.fetchall()]