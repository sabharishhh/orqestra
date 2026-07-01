"""Instrumented OpenAI chat completion wrapper.

Single chokepoint for all `gpt-5.4-mini` chat.completions calls in the live
pipeline. Emits `llm.call` log events with model, token counts, est_cost_usd,
purpose, and duration_ms.

DSPy calls (used by the Level 5 apex judge) bypass this wrapper because DSPy
owns the underlying API call; the apex_judge call site times itself separately.
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from openai import OpenAI

from observability import get_logger
from observability.pricing import gpt_54_mini_cost

logger = get_logger("observability.llm")

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def chat_completion(
    *,
    purpose: str,
    messages: list[dict],
    model: str = "gpt-5.4-mini",
    temperature: float = 0.0,
    **kwargs: Any,
) -> Any:
    """Instrumented chat.completions.create wrapper.

    `purpose` is required and must be one of:
        extraction | explainability | entity_suggestion |
        nli_fallback | resolution | induction

    Returns the raw OpenAI response object unchanged. Caller can keep using
    response.choices[0].message.content exactly as before.
    """
    start = time.perf_counter()
    response = None
    input_tokens = 0
    output_tokens = 0
    error: Optional[str] = None
    try:
        response = _get_client().chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            **kwargs,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
        return response
    except Exception as exc:
        error = type(exc).__name__
        raise
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        est_cost = gpt_54_mini_cost(input_tokens, output_tokens) if model.startswith("gpt-5.4-mini") else 0.0
        logger.info(
            "llm.call",
            model=model,
            purpose=purpose,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            est_cost_usd=round(est_cost, 6),
            duration_ms=duration_ms,
            error=error,
        )
        from observability import metrics
        metrics.observe_llm_call(purpose, input_tokens, output_tokens, duration_ms / 1000.0)