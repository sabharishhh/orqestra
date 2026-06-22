import os
import json
import uuid
import logging
from typing import Optional, List
from dataclasses import dataclass, field
from datetime import datetime

from openai import (
    OpenAI, 
    RateLimitError as OpenAIRateLimitError, 
    APITimeoutError as OpenAIAPITimeoutError, 
    APIConnectionError as OpenAIAPIConnectionError, 
    InternalServerError as OpenAIInternalServerError
)
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

# ==========================================
# LOGGING CONFIGURATION
# ==========================================
logger = logging.getLogger(__name__)

# ==========================================
# DATA STRUCTURES
# ==========================================

@dataclass
class SystemConfig:
    name: str
    provider: str            # "openai" | "custom"
    api_key: str
    model: str
    base_url: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.0  # ALWAYS 0.0 for deterministic probing

@dataclass
class OutputPair:
    probe_id: str            # uuid4
    question: str
    system_a_name: str
    system_a_output: str
    system_a_timestamp: datetime
    system_b_name: str
    system_b_output: str
    system_b_timestamp: datetime
    metadata: dict = field(default_factory=dict)

# ==========================================
# ERROR CLASSES
# ==========================================

class SystemConnectionError(Exception):
    """Raised when >50% of probes fail for a system."""
    pass

# ==========================================
# RETRY CONFIGURATION
# ==========================================

RETRYABLE_EXCEPTIONS = (
    OpenAIRateLimitError, 
    OpenAIAPITimeoutError, 
    OpenAIAPIConnectionError, 
    OpenAIInternalServerError
)

# ==========================================
# PUBLIC FUNCTIONS
# ==========================================

@retry(
    wait=wait_exponential(multiplier=2, min=2, max=4), # 2s, then 4s
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    reraise=True
)
def query_system(config: SystemConfig, prompt: str) -> str:
    """
    Queries an LLM endpoint deterministically.
    Automatically retries on rate limits and network timeouts.
    Auth errors or bad model names will fail immediately (non-retryable).
    """
    if config.provider not in ["openai", "custom"]:
        raise ValueError(f"Unsupported provider: '{config.provider}'. Only 'openai' and 'custom' are supported.")

    client_kwargs = {"api_key": config.api_key}
    if config.base_url:
        client_kwargs["base_url"] = config.base_url
        
    client = OpenAI(**client_kwargs)
    
    messages = []
    if config.system_prompt:
        messages.append({"role": "system", "content": config.system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    response = client.chat.completions.create(
        model=config.model,
        messages=messages,
        temperature=config.temperature
    )
    return response.choices[0].message.content or ""


def collect_pairs(questions: List[str], sys_a: SystemConfig, sys_b: SystemConfig) -> List[OutputPair]:
    """
    Executes a list of probe questions against two systems.
    Returns matched pairs where both systems successfully responded.
    Raises SystemConnectionError if >50% of probes fail for either system.
    """
    pairs = []
    sys_a_failures = 0
    sys_b_failures = 0
    total_questions = len(questions)

    if total_questions == 0:
        return pairs

    for idx, q in enumerate(questions, 1):
        out_a, out_b = None, None
        ts_a, ts_b = None, None
        
        # Query System A
        try:
            out_a = query_system(sys_a, q)
            ts_a = datetime.utcnow()
        except Exception as e:
            logger.warning(f"Failed to query '{sys_a.name}' for probe [{idx}/{total_questions}]: {e}")
            sys_a_failures += 1

        # Query System B
        try:
            out_b = query_system(sys_b, q)
            ts_b = datetime.utcnow()
        except Exception as e:
            logger.warning(f"Failed to query '{sys_b.name}' for probe [{idx}/{total_questions}]: {e}")
            sys_b_failures += 1

        # Only create a pair if BOTH responses were successfully collected
        if out_a is not None and out_b is not None:
            pairs.append(OutputPair(
                probe_id=str(uuid.uuid4()),
                question=q,
                system_a_name=sys_a.name,
                system_a_output=out_a,
                system_a_timestamp=ts_a,
                system_b_name=sys_b.name,
                system_b_output=out_b,
                system_b_timestamp=ts_b
            ))

    # Guardrail: Fail fast if either system is functionally dead
    if (sys_a_failures / total_questions) > 0.5:
        raise SystemConnectionError(f"System '{sys_a.name}' failed on >50% of probes ({sys_a_failures}/{total_questions}). Check credentials/rate limits.")
    if (sys_b_failures / total_questions) > 0.5:
        raise SystemConnectionError(f"System '{sys_b.name}' failed on >50% of probes ({sys_b_failures}/{total_questions}). Check credentials/rate limits.")

    return pairs


def load_probe_set(domain: str) -> List[str]:
    """
    Loads probe questions from the probes/{domain}.json file.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    probes_dir = os.path.join(base_dir, "probes")
    target_file = os.path.join(probes_dir, f"{domain}.json")

    if not os.path.exists(target_file):
        available = []
        if os.path.exists(probes_dir):
            available = [f.replace('.json', '') for f in os.listdir(probes_dir) if f.endswith('.json')]
        
        available_str = ', '.join(available) if available else 'None'
        raise FileNotFoundError(f"Probe set '{domain}' not found. Available domains: {available_str}")
    
    with open(target_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if not isinstance(data, list):
            raise ValueError(f"Probe file {domain}.json must contain a JSON array of strings.")
        return data