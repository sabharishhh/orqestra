import os
import json
import atexit
import threading
import httpx
import logging
from observability import get_logger
from typing import Dict, Any

logger = get_logger("Orqestra.SDK")

# F4.3 Compliance: Disk-backed buffer for crash resilience
BUFFER_FILE = os.environ.get("ORQESTRA_BUFFER_PATH", "/tmp/.orqestra_telemetry.jsonl")

class BackgroundTelemetryLogger:
    def __init__(self, endpoint_url: str, api_key: str, batch_size: int = 10, flush_interval_sec: float = 2.0):
        self.endpoint_url = endpoint_url
        self.api_key = api_key
        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.lock = threading.Lock()
        
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._worker, daemon=True)
        self._worker_thread.start()
        
        atexit.register(self.shutdown)

    def log(self, payload: Dict[str, Any]):
        """Thread-safe disk append."""
        try:
            with self.lock:
                with open(BUFFER_FILE, "a") as f:
                    f.write(json.dumps(payload) + "\n")
        except Exception as e:
            logger.debug(f"Orqestra buffer write failed: {e}")

    def _read_and_clear_batch(self) -> list:
        """Atomically reads up to batch_size lines and rewrites the remainder."""
        batch = []
        try:
            with self.lock:
                if not os.path.exists(BUFFER_FILE):
                    return batch
                    
                with open(BUFFER_FILE, "r") as f:
                    lines = f.readlines()
                    
                if not lines:
                    return batch
                    
                batch_lines = lines[:self.batch_size]
                remaining_lines = lines[self.batch_size:]
                
                # Parse the batch
                for line in batch_lines:
                    try:
                        batch.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
                        
                # Rewrite remainder (Atomic-like rewrite)
                with open(BUFFER_FILE, "w") as f:
                    f.writelines(remaining_lines)
                    
        except Exception as e:
            logger.debug(f"Orqestra buffer read failed: {e}")
            
        return batch

    def _worker(self):
        """Background thread that flushes the disk buffer to FastAPI."""
        headers = {
            "Authorization": f"Bearer {self.api_key}", # F7.3 Alignment
            "Content-Type": "application/json"
        }
        
        with httpx.Client(headers=headers, timeout=5.0) as client:
            while not self._stop_event.is_set():
                batch = self._read_and_clear_batch()
                
                if batch:
                    self._flush(client, batch)
                else:
                    # Sleep only if there was no work to do
                    self._stop_event.wait(self.flush_interval_sec)

    def _flush(self, client: httpx.Client, batch: list):
        try:
            payload = {"samples": batch}
            response = client.post(self.endpoint_url, json=payload)
            response.raise_for_status()
        except Exception as e:
            logger.debug(f"Orqestra Sync Failed. Re-queueing. {e}")
            # On failure, dump them back to the disk buffer
            for item in batch:
                self.log(item)

    def shutdown(self):
        self._stop_event.set()
        self._worker_thread.join(timeout=2.0)