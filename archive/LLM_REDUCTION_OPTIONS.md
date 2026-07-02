# Orqestra — LLM Call Reduction & Performance Options

**Date:** 2026-06-29
**Status:** Pre-pitch design memo. None of these are built. Numbers cite the Sprint 7.1 baseline.

---

## 1. Current LLM footprint

From the v3.4.0 instrumented baseline (15-sample burst):

| Call site | Model | Per 1K samples (extrapolated) | % of total |
|---|---|---:|---:|
| Claim extraction (`workers/claim_extractor.py`) | gpt-5.4-mini | ~$0.16 | **~80%** |
| Embeddings (`services/embed_client.py`) | text-embedding-3-small | ~$0.02 | ~10% |
| Level 5 apex judge (`workers/contradiction_detector.py`) | gpt-5.4-mini via DSPy | variable, fires on <5% | ~5% |
| Level 4 NLI fallback (`services/nli_classifier.py`) | gpt-5.4-mini | 0 when DeBERTa runs | ~0% |
| Resolution agent | gpt-5.4-mini | per-contradiction | ~3% |
| Entity name suggestion (auto-induction) | gpt-5.4-mini | nightly batch | ~2% |
| **Total at current scale** | | **~$0.19 / 1K samples** | |

**Extraction is 80% of the cost.** Every other optimization is a rounding error until extraction is solved.

### What the funnel already gives us

The 5-level detection funnel collapses LLM calls by ~95% relative to naive pairwise comparison. That work is done. The remaining cost is in the *unavoidable* per-claim work — extraction and embedding — not detection.

This memo focuses on reducing the per-claim cost, not the detection cost.

---

## 2. Local extraction model — highest leverage

### What it is

Replace `gpt-5.4-mini` SPO extraction with a local model. Three ascending options:

- **GLiNER (zero-shot NER) + rule-based SPO assembler** — ~50ms CPU, free, no training data needed
- **Fine-tuned DeBERTa for joint entity + relation extraction** — ~30ms CPU, requires ~500 labeled claims
- **Phi-3-mini or Qwen-2.5-1.5B for structured output** — ~200ms CPU / ~30ms GPU, matches gpt-5.4-mini quality once prompted/tuned

Extraction is structured JSON, not creative reasoning. `gpt-5.4-mini` is overpowered for this task. Domain-tuned small models routinely beat general mid-tier LLMs on extraction once they have a few hundred labeled examples.

### Positive impact

- **~80% LLM cost reduction.** Single biggest cost lever in the system.
- **Latency improvement.** Local CPU inference at 30–200ms vs. ~1.7s p50 for `gpt-5.4-mini` (current baseline). Sample-to-claim latency drops from ~2.5s to <1s.
- **Quality improvement (post-training).** Domain-tuned models hold the line on common patterns better than general LLMs. Once 500–1000 production claims are labeled, expect higher F1 than `gpt-5.4-mini`.
- **Privacy story.** On-prem extraction means customer data never leaves their environment. Real selling point for clinical and finance verticals.

### Negative impact / risk

- **Cold-start quality dip.** Pre-training-data, GLiNER is ~5–10% behind `gpt-5.4-mini` F1 on novel domains. Acceptable for the first design partner, painful for the second.
- **Training data dependency.** Quality jump requires labeled examples from the actual customer domain. Synthetic labels don't transfer.
- **Operational overhead.** New service to maintain, model versioning, retraining pipeline. Not zero-cost.
- **Hard cases still need LLM.** Long context, ambiguous structure, novel entity types — local model will fail, need fallback (covered in §6 adaptive routing).

### Effort

~2 weeks: model wiring + extraction service + fallback path. +1 week per customer domain for labeling and fine-tuning.

---

## 3. Local embeddings

### What it is

Replace `text-embedding-3-small` (1536-dim, OpenAI API) with a local model:

- **BGE-small-en-v1.5** — 384-dim, CPU-fast, comparable to text-embedding-3-small on most benchmarks
- **BGE-large-en-v1.5** — 1024-dim, beats text-embedding-3-small on retrieval benchmarks
- **nomic-embed-text-v1.5** — Matryoshka embeddings, runtime-selectable 256/512/768 dimensions

### Positive impact

- **~$0.02 per 1K samples saved.** Small absolute, but compounds at scale.
- **Lower latency.** ~10ms local vs. ~700ms p50 OpenAI API call (current baseline).
- **Equal or better retrieval quality.** BGE-large outperforms text-embedding-3-small on MTEB benchmarks.
- **Privacy.** Same story as local extraction.

### Negative impact / risk

- **Migration is non-trivial.** `VECTOR(1536)` → `VECTOR(384)` or `VECTOR(1024)` means re-embedding every claim in the database. pgvector HNSW index needs rebuild. Hours of downtime for an established estate.
- **No quality improvement on small estates.** Embedding quality matters at scale (>100K claims); below that, hard to measure improvement.
- **Don't do this piecemeal.** Has to happen during a planned re-platforming window.

### Effort

~1 sprint of engineering. Plus a migration window per existing customer.

---

## 4. Level 5 apex judge replacement

### What it is

The DSPy chain-of-thought on `gpt-5.4-mini` at Level 5 does real conditional-reasoning ("only if", "unless", "except when"). Replacements:

- **Fine-tuned DeBERTa with explicit conditional-constraint training set.** Catches the structural patterns DSPy is currently learning.
- **Rule-based pre-filter + smaller LLM.** Parse for conditional markers, route those to the LLM, send the rest to DeBERTa.

### Positive impact

- **Latency drop.** Current Level 5: 2473ms p50. DeBERTa: ~30ms.
- **Removes a real production failure mode.** Level 5 LLM calls fail under rate limits or API outages; local DeBERTa doesn't.

### Negative impact / risk

- **Recall loss on novel conditional structures.** DSPy generalizes; fine-tuned DeBERTa pattern-matches. ~5–10% recall drop expected on unseen patterns.
- **Marginal cost win.** Level 5 only fires on ~5% of claims that survive Levels 0–4. Absolute call volume is small. **Don't optimize this until extraction is solved.**
- **Spec already accepts gpt-5.4-mini here.** Pre-emptively replacing it is a deviation from the spec without clear justification.

### Effort

~1 sprint. Hold until production data shows Level 5 is actually a bottleneck.

---

## 5. Resolution agent — defer

### What it is

The resolution agent writes natural-language explanations + correction proposals. Replacements:

- Generate from a **template grounded in SCCG data**, with the LLM only filling natural-language summary slots
- Use a **smaller fine-tuned model** for the natural-language fragment

### Positive impact

- Per-contradiction cost reduction. Marginal.

### Negative impact / risk

- **The current freeform output is often the most useful thing the system produces.** Customers read these. The spec target ("design partner acts on explanation without extra investigation") is the highest-quality bar in the product.
- **Quality dip here costs adoption, not just dollars.** Bad explanations destroy trust faster than slow detections.

### Effort

Don't. Or rather: don't until well after extraction and embedding are won, AND a customer specifically asks for cheaper resolutions.

---

## 6. Adaptive routing — strict improvement

### What it is

Not a replacement, a router. A small classifier (sklearn LogisticRegression on simple features — claim length, entity novelty, structure complexity) predicts whether to route to local model or `gpt-5.4-mini`.

```
Easy extraction → local model (fast, free)
Hard extraction → gpt-5.4-mini (expensive, reliable)
```

### Positive impact

- **20–30% additional cost reduction on top of §2.** Stacks with local extraction.
- **Quality goes UP, not down.** Hard cases get the bigger model; easy cases stop wasting `gpt-5.4-mini` cycles. Net F1 improves.
- **Graceful degradation.** When OpenAI is rate-limited or down, all traffic falls to local. Better than current behavior (all extraction fails).

### Negative impact / risk

- **Requires labeled training data for the router.** ~1000 examples to classify "easy" vs. "hard" extractions. Bootstrapped from existing production traffic.
- **Adds a hidden variable.** Customer engineers may ask "why did this go to the cheap model?" — needs to be inspectable.

### Effort

~1 week, AFTER local extraction is in place. Standalone, it has nothing to route between.

---

## 7. Canon API as architectural cache

### What it is

Not an LLM optimization in the conventional sense, but the actual cost answer at the system level.

When agents call `Canon` *before* responding (request-path infrastructure), they get the canonical answer without their own RAG retrieval and without their own LLM hallucinating from scratch. **The customer's LLM cost drops, not just Orqestra's.**

```
Today: customer agent → RAG → LLM → output → Orqestra extracts → contradicts? → resolution
Canon: customer agent → Canon (cheap read) → LLM (smaller prompt) → output → Orqestra extracts ...
```

### Positive impact

- **Customer cost reduction, not just Orqestra cost.** This is the actual pitch story: "Orqestra reduces YOUR LLM bill, not ours."
- **Aligns with Monitor → Gate → Canon → OS strategic arc.** Canon is already the inflection point from observability to load-bearing infrastructure.
- **Compounds across agents.** N agents calling Canon means N customer LLM-cost reductions, while Orqestra's marginal cost per Canon call is one DB query.

### Negative impact / risk

- **Read-only Canon (today) doesn't update.** Full value requires bidirectional Canon — agents propose updates, org operator approves. That's Phase 2.
- **Needs customer agent rewiring.** Customer engineers have to insert the Canon call into their agent loops. Friction.
- **Hard to measure pre-deployment.** The cost reduction story is real but customer-side, only visible after integration.

### Effort

Read-side already built. Write-side (bidirectional Canon) is ~2 sprints. Customer integration is per-customer.

---

## 8. Recommended sequence

| Order | Option | When |
|---|---|---|
| 1 | **§7 Canon framing (existing read-side)** | Lead with this in NeuralCraft pitch. Costs nothing — it's the story for what's already shipped. |
| 2 | **§2 Local extraction model** | Post-pitch, if cost is a stated NeuralCraft concern. ~80% reduction, strict quality improvement post-training. |
| 3 | **§6 Adaptive routing** | Stacks on §2 for another 20–30%. Net F1 improves. |
| 4 | **§3 Local embeddings** | Bundle with the next major platform-rebuild window. Standalone migration is expensive. |
| 5 | **§4 Level 5 replacement** | Only if production data shows Level 5 is a real bottleneck. Hold otherwise. |
| 6 | **§5 Resolution agent local model** | Don't, unless customer explicitly asks. Quality risk outweighs cost win. |
| 7 | **§7 Canon write-side (Phase 2)** | Strategic, not tactical. Sequence with Resolution Agent ReAct loop. |

---

## 9. Headline number for the pitch

> "Cost per 1K samples is **$0.19 today**, with a clear path to **<$0.05** via local extraction + adaptive routing. Detection cost is already 95% reduced vs. naive pairwise comparison through the 5-level funnel. Canon API additionally reduces *the customer's* LLM bill by acting as a canonical-answer cache that displaces RAG-and-hallucinate cycles in their own agents."

That sentence answers the cost question without committing to delivery dates and reframes Orqestra as a customer-cost reducer rather than a new cost line item.

---

## 10. What NOT to do

- **Don't replace LLM calls before having production traffic to evaluate against.** Local models that look great on synthetic data routinely fail on real customer claims. Need real labeled examples from the first 1–3 design partners.
- **Don't optimize the resolution agent or Level 5 first.** Those are <5% of cost combined. Extraction is 80%. Work the leverage point.
- **Don't promise cost reductions in customer conversations beyond what's measurably delivered.** "$0.19 today, clear path to $0.05" is defensible. "$0.05 by Q1" is not.
- **Don't migrate embeddings piecemeal.** Schema cost is too high for incremental rollout. Bundle it with the next platform rebuild.

---

**End of memo.** Revisit after first design partner has 30 days of production traffic — that's when the labeled-data prerequisite for §2 is met.
