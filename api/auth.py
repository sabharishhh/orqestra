import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

# In production, this would be validated against a registered org database
API_KEY_NAME = "X-Orqestra-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)

def verify_api_key(api_key_header: str = Security(api_key_header)):
    """
    Validates incoming telemetry and write-hook requests.
    """
    expected_key = os.environ.get("ORQESTRA_ORG_KEY", "dev-test-key")
    if api_key_header != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Orqestra API Key",
        )
    return api_key_header