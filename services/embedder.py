import os
from openai import OpenAI
from tenacity import retry, wait_exponential, stop_after_attempt

_client = None
def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client

@retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(5))
def embed_text(text: str) -> list[float]:
    """Single-text embedding via text-embedding-3-small (1536-dim)."""
    resp = _get_client().embeddings.create(input=[text], model="text-embedding-3-small")
    return resp.data[0].embedding

@retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(5))
def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding for high-throughput paths."""
    resp = _get_client().embeddings.create(input=texts, model="text-embedding-3-small")
    return [d.embedding for d in sorted(resp.data, key=lambda x: x.index)]