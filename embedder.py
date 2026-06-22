import hashlib
import logging
import numpy as np
from typing import List, Dict
from dataclasses import dataclass
from openai import OpenAI

from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from output_collector import SystemConfig, RETRYABLE_EXCEPTIONS
from claim_extractor import ExtractedClaim

logger = logging.getLogger(__name__)

# ==========================================
# CONSTANTS & CONFIGURATION
# ==========================================

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
BATCH_SIZE_LIMIT = 100  # Safe batch limit for OpenAI embeddings API

# ==========================================
# DATA STRUCTURES
# ==========================================

@dataclass
class EmbeddedClaim:
    claim: ExtractedClaim
    embedding: np.ndarray    # shape (1536,)
    embedding_model: str

# ==========================================
# CACHING LAYER
# ==========================================

# In-memory cache to prevent redundant API calls for identical claim text
_embedding_cache: Dict[str, np.ndarray] = {}

def _get_cache_key(text: str) -> str:
    """Generates a deterministic MD5 hash for cache lookups."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()

# ==========================================
# CORE EMBEDDING LOGIC
# ==========================================

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
def _fetch_embeddings_from_api(texts: List[str], config: SystemConfig) -> List[np.ndarray]:
    """
    Makes the actual network call to OpenAI to fetch embeddings in batch.
    Wrapped in Tenacity for rate-limit and timeout resilience.
    """
    if not texts:
        return []
        
    client_kwargs = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
        
    client = OpenAI(**client_kwargs)
    
    try:
        response = client.embeddings.create(
            input=texts,
            model=DEFAULT_EMBEDDING_MODEL
        )
        # Ensure ordering matches the input
        embeddings = [np.array(data.embedding) for data in sorted(response.data, key=lambda x: x.index)]
        return embeddings
    except Exception as e:
        logger.error(f"OpenAI Embedding API failed: {e}")
        raise

def embed_batch(texts: List[str], config: SystemConfig) -> List[np.ndarray]:
    """
    Smart batch embedder. Checks cache first, only fetches missing vectors 
    from the API, updates the cache, and returns the complete ordered list.
    """
    results: List[np.ndarray | None] = [None] * len(texts)
    missing_indices: List[int] = []
    missing_texts: List[str] = []
    
    # 1. Check cache
    for i, text in enumerate(texts):
        key = _get_cache_key(text)
        if key in _embedding_cache:
            results[i] = _embedding_cache[key]
        else:
            missing_indices.append(i)
            missing_texts.append(text)
            
    # 2. Fetch missing in chunks to respect API limits
    if missing_texts:
        logger.debug(f"Cache miss for {len(missing_texts)}/{len(texts)} embeddings. Fetching from API...")
        
        for i in range(0, len(missing_texts), BATCH_SIZE_LIMIT):
            chunk_texts = missing_texts[i : i + BATCH_SIZE_LIMIT]
            chunk_indices = missing_indices[i : i + BATCH_SIZE_LIMIT]
            
            chunk_embeddings = _fetch_embeddings_from_api(chunk_texts, config)
            
            # 3. Update cache and results array
            for idx, text, emb in zip(chunk_indices, chunk_texts, chunk_embeddings):
                _embedding_cache[_get_cache_key(text)] = emb
                results[idx] = emb
                
    return results

def embed_claims(claims: List[ExtractedClaim], config: SystemConfig) -> List[EmbeddedClaim]:
    """
    Takes a list of ExtractedClaims, generates their embeddings efficiently,
    and returns them wrapped in EmbeddedClaim dataclasses.
    """
    if not claims:
        return []
        
    # We embed the claim_text (subject + predicate + object + context) to capture full semantics
    texts_to_embed = [
        f"{c.subject} {c.predicate} {c.obj}. Context: {c.context}".strip()
        for c in claims
    ]
    
    embeddings = embed_batch(texts_to_embed, config)
    
    embedded_claims = []
    for claim, emb in zip(claims, embeddings):
        embedded_claims.append(EmbeddedClaim(
            claim=claim,
            embedding=emb,
            embedding_model=DEFAULT_EMBEDDING_MODEL
        ))
        
    return embedded_claims

# ==========================================
# MATH UTILITIES
# ==========================================

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Computes the cosine similarity between two vectors.
    Returns a float between -1.0 and 1.0.
    """
    # OpenAI embeddings are pre-normalized, but we calculate safely to be deterministic
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
        
    return float(np.dot(a, b) / (norm_a * norm_b))