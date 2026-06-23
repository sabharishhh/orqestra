import os
import atexit
import threading
import queue
import httpx
import logging
from typing import Dict, Any

logger = logging.getLogger("Orqestra.SDK")

class BackgroundTelemetryLogger:
    def __init__(self, endpoint_url: str, api_key: str, batch_size: int = 10, flush_interval_sec: float = 1.0):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        
        self.queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        # Ensure we flush remaining logs when the agent script exits
        atexit.register(self.shutdown)

    def log(self, payload: Dict[str, Any]):
        """Non-blocking queue insertion."""
        self.queue.put(payload)

    def _worker(self):
        """Background thread that batches and sends telemetry."""
        headers = {"X-Orqestra-Key": self.api_key}
        # Use an HTTPX client for connection pooling
        with httpx.Client(headers=headers, timeout=5.0) as client:
            while not self._stop_event.is_set():
                batch = []
                try:
                    # Wait for items, up to the flush interval
                    item = self.queue.get(timeout=self.flush_interval_sec)
                    batch.append(item)
                    
                    # Grab remaining items up to batch size without waiting
                    while len(batch) < self.batch_size:
                        try:
                            batch.append(self.queue.get_nowait())
                        except queue.Empty:
                            break
                            
                except queue.Empty:
                    # Timeout reached, continue loop
                    pass

                if batch:
                    self._flush(client, batch)

    def _flush(self, client: httpx.Client, batch: list):
        """Sends the payload array to the FastAPI ingestion endpoint."""
        try:
            # We assume batch mode endpoint is available: POST /systems/{id}/samples/batch
            payload = {"samples": batch}
            response = client.post(self.endpoint_url, json=payload)
            response.raise_for_status()
        except Exception as e:
            logger.debug(f"Orqestra Telemetry Sync Failed (agent unharmed): {e}")

    def shutdown(self):
        """Gracefully flushes remaining items before exit."""
        self._stop_event.set()
        self._worker_thread.join(timeout=2.0)