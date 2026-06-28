import time
import hmac
import hashlib
from fastapi import Security, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from core.database import SessionLocal
from models.database import System
from observability.context import bind_tenant 

# Enforce Bearer token standard per the architectural spec
security = HTTPBearer()

def get_db():
    """Dependency generator for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
):
    """
    Validates incoming telemetry requests against the registered systems database.
    Enforces standard Bearer token format and cryptographic hashing.
    """
    token = credentials.credentials
    
    # 1. Enforce Token Format (oq-{64-char-hex})
    if not token.startswith("oq-") or len(token) != 67:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format. Key must follow 'oq-{64-char-hex}' format.",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    # 2. Verify Cryptographic Hash against the Database
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    system = db.query(System).filter(System.api_key_hash == token_hash).first()
    
    if not system:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key or System not registered.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    bind_tenant(
        tenant_id=str(system.org_id),
        org_slug=system.organization.slug,
    )
    
    # Return the full system object to scope all downstream actions
    return system

async def verify_write_hook_signature(
    request: Request,
    system: System = Depends(verify_api_key)
):
    """
    F7.1 Compliance: Enforces HMAC-SHA256 request signing for write hooks 
    to prevent malicious SCCG poisoning.
    """
    # Extract the raw API key from the verified Bearer token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
        
    api_key = auth_header.split(" ")[1]
    
    # Extract Signature Headers
    timestamp = request.headers.get("X-Orqestra-Timestamp")
    provided_sig = request.headers.get("X-Orqestra-Signature")
    
    if not timestamp or not provided_sig:
        raise HTTPException(status_code=401, detail="Missing HMAC signature headers.")
        
    # Replay attack prevention (5 minute window)
    try:
        if abs(time.time() - float(timestamp)) > 300:
            raise HTTPException(status_code=401, detail="Request timestamp expired. Possible replay attack.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp format.")

    # Read raw body for cryptographic validation
    body = await request.body()
    
    # Compute Expected Signature: hmac.new(api_key, "{timestamp}:{body}")
    message = f"{timestamp}:{body.decode()}".encode()
    expected_sig = hmac.new(api_key.encode(), message, hashlib.sha256).hexdigest()
    
    # Secure comparison
    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=401, detail="Invalid HMAC signature.")
        
    return system