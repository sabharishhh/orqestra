"""
NLI classifier service. Routes Level 4 of the detection funnel to either
the local DeBERTa cross-encoder (production GPU envs) or gpt-5.4-mini
(dev / docker / no-GPU envs).

Controlled by env var: ORQESTRA_NLI_BACKEND = "openai" (default) | "local"

Spec compliance: spec lists DeBERTa-v3-small as primary, gpt-5.4-mini as
fallback. This service treats both as first-class and picks at runtime.
"""
import os
import json
import logging
import httpx
from openai import OpenAI, APIConnectionError, RateLimitError, APITimeoutError
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

NLI_BACKEND = os.environ.get("ORQESTRA_NLI_BACKEND", "openai").lower()
LOCAL_MODEL_NAME = os.environ.get(
    "ORQESTRA_LOCAL_NLI_MODEL",
    "MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli"
)


# ==========================================
# OPENAI BACKEND (default)
# ==========================================
NLI_SYSTEM_PROMPT = """You are a strict NLI (Natural Language Inference) classifier.
Given two claims, classify their logical relationship.

Return ONLY a single JSON object:
{
  "label": "CONTRADICTION" | "ENTAILMENT" | "NEUTRAL",
  "confidence": <float between 0.0 and 1.0>
}

Rules:
- CONTRADICTION: the two claims cannot both be true at the same time.
- ENTAILMENT: claim B is logically implied by claim A (or vice versa).
- NEUTRAL: the claims neither contradict nor entail each other.

Pay attention to conditional constraints, numeric value differences, and
directive opposites (must vs must not, include vs exclude)."""


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=15),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((APIConnectionError, RateLimitError, APITimeoutError, httpx.HTTPError)),
    reraise=True
)
def _classify_openai(text_a: str, text_b: str) -> dict:
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-5.4-mini",
        messages=[
            {"role": "system", "content": NLI_SYSTEM_PROMPT},
            {"role": "user", "content": f"Claim A: \"{text_a}\"\n\nClaim B: \"{text_b}\""}
        ],
        temperature=0.0,
    )
    raw = response.choices[0].message.content.strip()
    if raw.startswith("```json"): raw = raw[7:]
    if raw.endswith("```"): raw = raw[:-3]
    data = json.loads(raw.strip())

    label = str(data.get("label", "NEUTRAL")).upper()
    if label not in ("CONTRADICTION", "ENTAILMENT", "NEUTRAL"):
        label = "NEUTRAL"
    confidence = float(data.get("confidence", 0.0))
    confidence = max(0.0, min(1.0, confidence))
    return {"prediction": label, "confidence": confidence}


# ==========================================
# LOCAL DEBERTA BACKEND (production w/ GPU)
# ==========================================
class _LocalBouncer:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._tokenizer = None
        self._model = None
        self._torch = None

    def _load(self):
        if self._model is not None: return
        logger.info(f"Loading local NLI model ({self.model_name})...")
        import torch
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self._model = self._model.to("mps")
        elif torch.cuda.is_available():
            self._model = self._model.to("cuda")

    def evaluate(self, text_a: str, text_b: str) -> dict:
        self._load()
        inputs = self._tokenizer(text_a, text_b, padding=True, truncation=True,
                                  max_length=512, return_tensors="pt")
        device = next(self._model.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with self._torch.no_grad():
            outputs = self._model(**inputs)
            probs = self._torch.softmax(outputs.logits[0], dim=0).tolist()
        id2label = self._model.config.id2label
        id_mapping = {int(k): str(v).upper() for k, v in id2label.items()}
        if not any(k in ["CONTRADICTION", "ENTAILMENT", "NEUTRAL"] for k in id_mapping.values()):
            id_mapping = {0: "CONTRADICTION", 1: "ENTAILMENT", 2: "NEUTRAL"}
        max_idx = probs.index(max(probs))
        return {"prediction": id_mapping.get(max_idx, "NEUTRAL"), "confidence": probs[max_idx]}


_local_bouncer = None
def _get_local() -> _LocalBouncer:
    global _local_bouncer
    if _local_bouncer is None:
        _local_bouncer = _LocalBouncer(LOCAL_MODEL_NAME)
    return _local_bouncer


# ==========================================
# PUBLIC API
# ==========================================
def classify_pair(text_a: str, text_b: str) -> dict:
    """
    Returns {"prediction": "CONTRADICTION"|"ENTAILMENT"|"NEUTRAL",
             "confidence": float}.
    """
    if NLI_BACKEND == "local":
        try:
            return _get_local().evaluate(text_a, text_b)
        except Exception as e:
            logger.error(f"Local NLI failed, falling back to OpenAI: {e}")
            return _classify_openai(text_a, text_b)
    return _classify_openai(text_a, text_b)