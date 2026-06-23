import functools
import warnings
from .client import get_logger

# F4.2 Compliance: Guard against upstream API structure changes
try:
    import openai
    if not openai.__version__.startswith("1."):
        warnings.warn(
            f"\n[ORQESTRA SDK] WARNING: Untested OpenAI version detected (v{openai.__version__}). "
            "Orqestra telemetry monkey-patching is only certified for v1.x.x. "
            "Telemetry may silently fail.\n", 
            UserWarning
        )
except ImportError:
    pass

def wrap_openai(client):
    """Wraps an official OpenAI Python Client."""
    original_create = client.chat.completions.create

    @functools.wraps(original_create)
    def wrapped_create(*args, **kwargs):
        response = original_create(*args, **kwargs)
        
        try:
            messages = kwargs.get("messages", [])
            system_prompts = [m["content"] for m in messages if m.get("role") == "system"]
            assistant_output = response.choices[0].message.content
            
            full_context = "\n".join(system_prompts) + "\n\n" + assistant_output
            
            logger = get_logger()
            logger.log({
                "text": full_context,
                "metadata": {
                    "model": kwargs.get("model", "unknown"),
                    "sdk_origin": "openai_wrapper"
                },
                "vector_clock": {}
            })
        except Exception:
            pass
            
        return response

    client.chat.completions.create = wrapped_create
    return client

def on_write(text: str, metadata: dict = None, vector_clock: dict = None):
    """Direct Write-Hook for arbitrary architectures."""
    try:
        logger = get_logger()
        logger.log({
            "text": text,
            "metadata": metadata or {"sdk_origin": "direct_write_hook"},
            "vector_clock": vector_clock or {}
        })
    except Exception:
        pass