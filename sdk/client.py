import os
from .batch_logger import BackgroundTelemetryLogger

# Global singleton logger
_telemetry_logger = None

def init(system_id: str, orqestra_api_key: str = None, orqestra_url: str = "http://localhost:8000"):
    """
    Initializes the Orqestra SDK for a specific Agent System.
    """
    global _telemetry_logger
    
    key = orqestra_api_key or os.environ.get("ORQESTRA_ORG_KEY", "dev-test-key")
    if not key:
        raise ValueError("Orqestra API Key is required for SDK telemetry.")
        
    # Standardize the endpoint path based on the FastAPI routing we built
    endpoint = f"{orqestra_url.rstrip('/')}/systems/{system_id}/samples/batch"
    
    _telemetry_logger = BackgroundTelemetryLogger(
        endpoint_url=endpoint,
        api_key=key
    )
    return _telemetry_logger

def get_logger() -> BackgroundTelemetryLogger:
    """Returns the global logger instance."""
    if _telemetry_logger is None:
        raise RuntimeError("Orqestra SDK not initialized. Call orqestra.init(system_id) first.")
    return _telemetry_logger