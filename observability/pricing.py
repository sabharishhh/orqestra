"""LLM and embedding pricing constants.

Per-1M-token rates in USD. Update these when provider pricing changes.

Source: https://openai.com/api/pricing/
Last verified: 2026-06-28
"""

# gpt-5.4-mini
GPT_54_MINI_INPUT_PER_1M_USD = 0.15
GPT_54_MINI_OUTPUT_PER_1M_USD = 0.60

# text-embedding-3-small
EMBEDDING_3_SMALL_PER_1M_USD = 0.02


def gpt_54_mini_cost(input_tokens: int, output_tokens: int) -> float:
    """Estimated USD cost for a gpt-5.4-mini call."""
    return (
        (input_tokens / 1_000_000) * GPT_54_MINI_INPUT_PER_1M_USD
        + (output_tokens / 1_000_000) * GPT_54_MINI_OUTPUT_PER_1M_USD
    )


def embedding_3_small_cost(tokens: int) -> float:
    """Estimated USD cost for a text-embedding-3-small call."""
    return (tokens / 1_000_000) * EMBEDDING_3_SMALL_PER_1M_USD