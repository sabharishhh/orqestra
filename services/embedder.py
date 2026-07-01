"""Sprint 7.1 shim: re-exports the instrumented embedding client.

Original uninstrumented implementations have been moved to
`services.embed_client`. This file remains as a compatibility shim so existing
`from services.embedder import embed_text, embed_batch` imports keep working.
"""

from services.embed_client import embed_text, embed_batch

__all__ = ["embed_text", "embed_batch"]