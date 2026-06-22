import functools
from .client import get_logger

def wrap_openai(client):
    """
    Wraps an official OpenAI Python Client.
    Intercepts chat.completions.create to extract context for Orqestra.
    """
    original_create = client.chat.completions.create

    @functools.wraps(original_create)
    def wrapped_create(*args, **kwargs):
        # 1. Execute the actual LLM call
        response = original_create(*args, **kwargs)
        
        # 2. Extract Context (System prompt + Assistant Output)
        try:
            # We want to capture what the agent knows (system prompt) 
            # and what it concluded (assistant text)
            messages = kwargs.get("messages", [])
            system_prompts = [m["content"] for m in messages if m.get("role") == "system"]
            assistant_output = response.choices[0].message.content
            
            # Combine them into the raw text block that our Extractor will parse
            full_context = "\n".join(system_prompts) + "\n\n" + assistant_output
            
            # 3. Fire to background queue silently
            logger = get_logger()
            logger.log({
                "text": full_context,
                "metadata": {
                    "model": kwargs.get("model", "unknown"),
                    "sdk_origin": "openai_wrapper"
                }
            })
        except Exception:
            # Fail silently so we never break the host application
            pass
            
        return response

    # Monkey patch the client
    client.chat.completions.create = wrapped_create
    return client


def on_write(text: str, metadata: dict = None):
    """
    Direct Write-Hook.
    Used by arbitrary architectures (LangChain, CrewAI, Autogen) to push state directly.
    """
    try:
        logger = get_logger()
        logger.log({
            "text": text,
            "metadata": metadata or {"sdk_origin": "direct_write_hook"}
        })
    except Exception:
        pass