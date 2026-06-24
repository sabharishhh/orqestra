import functools
from typing import Any, Dict, Optional
from .client import get_logger

class OrquestraIngestor:
    """Manual context logger for systems that don't want wrapper injection."""
    def __init__(self, system_id: str, api_key: str, client_instance: Any):
        self.system_id = system_id
        self.client = client_instance
        
    def log(self, text: str, metadata: dict = None, vector_clock: dict = None):
        payload = {
            "text": text,
            "metadata": metadata or {},
            "vector_clock": vector_clock
        }
        # Safety check depending on how the client was initialized
        if hasattr(self.client, 'background_logger'):
            self.client.background_logger.log(payload)
        else:
            self.client.log(payload)

def on_write(text: str, metadata: dict = None, vector_clock: dict = None):
    """Direct write hook for the SDK using the globally initialized client."""
    client = get_logger()
    if not client:
        import logging
        logging.getLogger("Orqestra.SDK").warning("SDK not initialized. Call orqestra.init() first.")
        return

    payload = {
        "text": text,
        "metadata": metadata or {},
        "vector_clock": vector_clock
    }
    
    # FIX: get_logger() returns the BackgroundTelemetryLogger instance directly
    client.log(payload)

def wrap_openai(client: Any, orqestra_client: Any) -> Any:
    """Wraps OpenAI API ChatCompletions."""
    original_create = client.chat.completions.create
    
    @functools.wraps(original_create)
    def patched_create(*args, **kwargs):
        response = original_create(*args, **kwargs)
        if response.choices and len(response.choices) > 0:
            text = response.choices[0].message.content
            payload = {
                "text": text,
                "metadata": {"provider": "openai", "model": kwargs.get("model")}
            }
            if hasattr(orqestra_client, 'background_logger'):
                orqestra_client.background_logger.log(payload)
            else:
                orqestra_client.log(payload)
        return response
        
    client.chat.completions.create = patched_create
    return client

def wrap_anthropic(client: Any, orqestra_client: Any) -> Any:
    """F4.2 Compliance: Wrapper for Anthropic SDK Messages API."""
    original_create = client.messages.create
    
    @functools.wraps(original_create)
    def patched_create(*args, **kwargs):
        response = original_create(*args, **kwargs)
        
        # Anthropic returns blocks of text, we concat them
        if hasattr(response, 'content'):
            text = "".join(block.text for block in response.content if hasattr(block, 'text'))
            payload = {
                "text": text,
                "metadata": {"provider": "anthropic", "model": kwargs.get("model")}
            }
            if hasattr(orqestra_client, 'background_logger'):
                orqestra_client.background_logger.log(payload)
            else:
                orqestra_client.log(payload)
        return response
        
    client.messages.create = patched_create
    return client

def wrap_langchain(llm: Any, orqestra_client: Any) -> Any:
    """F4.2 Compliance: Wrapper for LangChain Chat Models."""
    original_invoke = llm.invoke
    
    @functools.wraps(original_invoke)
    def patched_invoke(*args, **kwargs):
        response = original_invoke(*args, **kwargs)
        
        # Depending on the LangChain object, content is a str or an AIMessage attribute
        text = response.content if hasattr(response, 'content') else str(response)
        
        payload = {
            "text": text,
            "metadata": {"provider": "langchain", "type": type(llm).__name__}
        }
        if hasattr(orqestra_client, 'background_logger'):
            orqestra_client.background_logger.log(payload)
        else:
            orqestra_client.log(payload)
        return response
        
    llm.invoke = patched_invoke
    return llm