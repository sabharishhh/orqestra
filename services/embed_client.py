"""Instrumented OpenAI embeddings wrapper.

Single chokepoint for all `text-embedding-3-small` calls in the live pipeline.
Emits `embedding.call` log events with model, token count, vector count, dim,
est_cost_usd, and duration_ms.
"""

from __future__ import annotations

import os
import time
from typing import Optional

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from observability import get_logger
from observability.pricing import embedding_3_small_cost

logger = get_logger("observability.embedding")

_client: Optional[OpenAI] = None
_EXPECTED_DIM = 1536


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def _emit(model: str, tokens: int, vectors: int, dim: int, duration_ms: float, error: Optional[str]) -> None:
    logger.info(
        "embedding.call",
        model=model,
        input_tokens=tokens,
        vector_count=vectors,
        dim=dim,
        est_cost_usd=round(embedding_3_small_cost(tokens), 6),
        duration_ms=duration_ms,
        error=error,
    )
    from observability import metrics
    metrics.observe_embedding_call(tokens, duration_ms / 1000.0)


@retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(5))
def embed_text(text: str, model: str = "text-embedding-3-small") -> list[float]:
    """Single-text embedding via text-embedding-3-small (1536-dim)."""
    start = time.perf_counter()
    tokens = 0
    dim = 0
    error: Optional[str] = None
    try:
        resp = _get_client().embeddings.create(input=[text], model=model)
        vector = resp.data[0].embedding
        dim = len(vector)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "total_tokens", 0) or 0
        return vector
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _emit(model, tokens, 1, dim, duration_ms, error)


@retry(wait=wait_exponential(multiplier=2, min=2, max=30), stop=stop_after_attempt(5))
def embed_batch(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Batch embedding for high-throughput paths."""
    start = time.perf_counter()
    tokens = 0
    dim = 0
    vectors_out: list[list[float]] = []
    error: Optional[str] = None
    try:
        resp = _get_client().embeddings.create(input=texts, model=model)
        vectors_out = [d.embedding for d in sorted(resp.data, key=lambda x: x.index)]
        dim = len(vectors_out[0]) if vectors_out else 0
        usage = getattr(resp, "usage", None)
        if usage is not None:
            tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "total_tokens", 0) or 0
        return vectors_out
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        _emit(model, tokens, len(vectors_out), dim, duration_ms, error)