# Orqestra — Data Structure Options for Contradiction Detection

**Date:** 2026-06-29
**Status:** Pre-pitch design exploration. None of the proposed structures are built. Document is a design memo, not a sprint plan.

---

## 1. Current implementation

Orqestra today maintains two structures and queries derivatively from them.

### SCCG — Sparse Causal Claim Graph

Append-only DAG, one node per `Claim`, edges via `parent_claim_id`. Captures **causal dependence**: which claim was derived from which.

```
Claim (table)
  id, org_id, system_id, entity_hint
  subject, predicate, object, embedding (1536-dim)
  vector_clock (JSONB), parent_hashes, parent_claim_id
  extracted_at
```

Cross-agent parent pointers (Sprint 6.5) mean Agent A's claim can have Agent B's claim as parent — enables real LCAs and the lineage graph we ship today.

### OBG — Organizational Belief Graph

Materialized point data, one row per `(org_id, system_id, entity_name)` tuple. Captures **belief location** per agent.

```
EntityBeliefState (table)
  org_id, system_id, entity_name
  centroid_embedding, variance
  sample_count, confidence
  last_updated_at
```

Updated incrementally on every claim via Welford's online algorithm. Used at Level 0 of the funnel.

### How contradictions are stored

`Contradiction` is a pairwise row between two `Claim` ids:

```
Contradiction (table)
  id, org_id
  claim_a_id, claim_b_id
  severity, cost_usd, nli_score, status
  detected_at
```

### What this captures well

- **Causal lineage** (SCCG) — what derived from what, with cross-agent LCAs
- **Per-agent belief location** (OBG) — where each agent stands on each entity
- **Pairwise contradictions** — A vs B disagreement on entity X

### What this does NOT capture as first-class

- **Disagreement structure across the estate.** "Which entities are currently contested by 2+ agents" requires a full OBG scan. There's no materialized map.
- **N-way disagreement.** If 3 agents disagree about one entity, we store 3 pairwise rows instead of one estate-wide consensus failure.
- **Single-agent self-contradictions inside one session.** The funnel only looks cross-agent.
- **Semantic clusters that cross entity boundaries.** If `entity_resolver` misses unifying "copay" and "patient cost share", contradictions between them are structurally invisible.
- **Inter-agent agreement history.** No record of which agent pairs tend to disagree, so the funnel can't use priors.
- **Probabilistic structure.** OBG centroids are point estimates, not posteriors.

The six structures below address these gaps.

---

## 2. Belief Disagreement Graph (BDG)

### What it is

A derived graph materialized alongside OBG. Nodes are `(entity, agent)` OBG rows. Edges exist between two nodes when their centroids diverge above a threshold and both have `sample_count >= bootstrap_min`.

```
BeliefDisagreement (proposed table)
  id, org_id, entity_name
  system_a_id, system_b_id
  centroid_distance, both_above_bootstrap
  first_observed_at, last_updated_at
  active (boolean)
```

Maintained incrementally by `obg_updater`: every time an OBG row's centroid moves, recompute its edges to other OBG rows for the same entity. O(systems) per update, not O(claims).

### Positive impact on contradiction detection

- **O(1) disagreement-map query** instead of full OBG scan. Dashboard can render "live coherence state" in one query.
- **Materializes Level 0 work.** Level 0 currently recomputes pairwise centroid distances on every detection cycle. BDG caches them.
- **Surfaces contradictions earlier.** A high-distance BDG edge fires before any single new claim triggers the funnel — useful for proactive alerts on slow-emerging belief drift.
- **Pitch story.** Turns "we detect contradictions reactively" into "we maintain a live disagreement map." Single most visible artifact for a dashboard.

### Negative impact / risk

- **Write amplification.** Every OBG update now also writes BDG edges. ~5–10% more write load on `obg_updater`. Measurable but small.
- **Stale-edge risk.** If `obg_updater` falls behind, BDG lags. Need a periodic reconciliation job or accept eventual consistency.
- **Doesn't change WHAT we detect.** BDG accelerates queries and visualization, not detection accuracy. Easy to oversell.

### Effort

Half a sprint. New table, ~150 lines in `obg_updater`, dashboard panel.

---

## 3. Session/conversation DAG

### What it is

Add `session_id` (already in spec as `output_samples.session_id` but not used by detection) to `Claim`. Detect contradictions where `claim_a.session_id == claim_b.session_id` AND `claim_a.system_id == claim_b.system_id` — i.e. an agent contradicting itself inside one conversation.

Detection path: a new sub-funnel that runs only on intra-session pairs, bypassing the cross-system bootstrap gate.

### Positive impact

- **Catches a failure mode we currently miss entirely.** Single-agent reasoning self-contradiction is a real bug in production agents (reasoning loops, RAG context shifts mid-conversation, tool-call result reinterpretation).
- **Faster signal for customers.** Self-contradictions show up within one session — minutes — vs. cross-agent which needs multiple agents to have spoken.
- **Strengthens the "no existing tool detects this" pitch claim.** Per-system observability tools don't catch self-contradiction either, because they're built around tracing, not semantic comparison.

### Negative impact / risk

- **Higher false-positive rate.** Agents legitimately update their stance within a conversation ("on reflection..."). Hard to distinguish from contradiction without conversational context.
- **Session boundaries are fuzzy.** Some frameworks don't have a clear session concept; coverage will vary by integration.
- **Requires UX work.** A self-contradiction alert needs different framing than a cross-agent one — "your agent contradicted itself" reads as an attack on the customer's product.

### Effort

~1 sprint. Schema is already there (`session_id` column exists). Logic is the new path through the funnel + UI framing.

---

## 4. Semantic claim clustering across entity boundaries

### What it is

Periodic clustering (HDBSCAN or agglomerative) over `claim.embedding`, ignoring `entity_hint`. Surfaces clusters that mix entity hints. A cluster spanning multiple `entity_hint` values is a signal that `entity_resolver` failed to unify what are actually the same concept.

```
SemanticCluster (proposed table)
  id, org_id, cluster_centroid
  member_claim_ids, member_entity_hints
  inferred_canonical_entity (nullable)
  status: pending_review | merged | rejected
```

A nightly job runs the clustering; high-coherence multi-entity clusters become entity-merge candidates for the existing induction worker.

### Positive impact

- **Catches missed entity unifications.** If "copay" and "patient cost share" never got merged by the resolver, contradictions between them are invisible. Clustering catches that.
- **Discovers entity hierarchies.** A cluster spanning "metformin", "metformin HCl", "metformin extended-release" suggests a parent-child relationship the canonical vocabulary should encode.
- **Feeds existing induction workflow.** Doesn't replace it, augments it. Same human-review UI.

### Negative impact / risk

- **Compute cost on large estates.** HDBSCAN over 100K+ claims per org is non-trivial; needs sampling or per-window scoping.
- **High noise rate.** Most multi-entity clusters will be false positives (genuinely different entities that happen to embed similarly). Review burden falls on the org operator.
- **Doesn't help if entity_resolver is already good.** Diminishing returns once canonical vocabularies are mature.

### Effort

~1.5 sprints. Clustering implementation is cheap, the review UI and merge workflow are the bulk of the work.

---

## 5. Contradiction hypergraph

### What it is

Replace pairwise `Contradiction` rows with hyperedges that span N claims when the same entity has 3+ disagreeing agents. Same underlying data, different shape.

```
ContradictionGroup (proposed table)
  id, org_id, entity_name
  claim_ids (array of UUIDs)
  agent_ids (array of UUIDs)
  severity, total_cost_usd, status

ContradictionMembership (proposed table — join)
  group_id, claim_id, position_centroid
```

Detection flow: when a new contradiction is detected on `(entity_X, agent_A vs agent_B)`, check if `entity_X` already has an open `ContradictionGroup`. If yes, add the new agent to it. If no, create one.

### Positive impact

- **More honest representation.** Three agents disagreeing about `metformin_dosage` is one consensus failure, not three pairwise alerts. Matches how humans think about it.
- **Reduces alert fatigue (F8.3).** One hyperedge replaces N(N-1)/2 pairwise alerts.
- **Better severity math.** Cost can be computed per-group instead of summed pairwise (avoids double-counting).
- **Pitch story.** "We don't just detect pairs of disagreeing agents — we map estate-wide consensus failures."

### Negative impact / risk

- **Migration cost.** Existing `Contradiction` rows need backfilling into groups. Or maintain both, which doubles state.
- **Edge cases get harder.** "Agent C agrees with A but disagrees with B about the same entity" — what's the group shape? Needs explicit position clustering inside the hyperedge.
- **Resolution gets more complex.** A pairwise resolution is "update KB X." A group resolution is "decide which of N positions is canonical, then update K KBs." More valuable, more work.

### Effort

~1 sprint for the schema and detection logic. +1 sprint for resolution agent updates. +0.5 sprint for dashboard. ~2.5 sprints total.

---

## 6. Agent agreement profile (learned priors)

### What it is

Maintain a rolling per-agent-pair agreement score, bucketed by entity category. Use it to bias the funnel's NLI floor.

```
AgentAgreementProfile (proposed table)
  org_id, system_a_id, system_b_id
  entity_category
  agreement_score (float)
  total_comparisons, contradictions_confirmed
  last_updated_at
```

Funnel modification: at Level 4, look up the agreement profile for the agent pair + entity category. Lower the NLI floor for historically antagonistic pairs (catch more), raise it for historically agreeable pairs (reduce false positives, save LLM cost).

### Positive impact

- **Improves precision over time.** Stable agent pairs stop firing low-confidence NLI for entities they reliably agree on. Antagonistic pairs get tighter scrutiny.
- **Net LLM cost reduction.** Estimate ~20–30% fewer Level 5 calls once profiles stabilize (3–6 months of production data).
- **Quantifies estate trust topology.** "Agents X and Y agree 98% of the time" is itself a useful metric for the customer.
- **Feeds research roadmap.** This is what "learned belief state estimation" (Tier 2 research) points at architecturally.

### Negative impact / risk

- **Needs months of production data to be useful.** Cold-start period where profiles are unreliable. Risk of locking in early biases.
- **Can mask genuine new contradictions.** If A and B have historically agreed about pricing, the system trusts them more, and a new pricing contradiction needs more evidence to surface.
- **Adds a hidden variable to the funnel.** Customers may want to know "why did this fire" — answer becomes "because of historical priors" which is harder to debug than "because cosine > threshold."

### Effort

~1.5 sprints for the schema, update logic, and funnel integration. Real value only after 3+ months of production data.

---

## 7. Probabilistic graphical model over OBG

### What it is

Replace OBG centroid point estimates with a proper Bayesian belief network. Each claim is evidence updating posteriors over entity attributes. Contradictions emerge when posterior modes from different agents are mutually incompatible under the model.

Schema implication: OBG becomes a much richer structure (distributions, not centroids). Detection becomes Bayesian inference, not cosine distance.

### Positive impact

- **Principled uncertainty handling.** Today we have `confidence` as a heuristic. PGM gives real posteriors.
- **Better handling of low-sample entities.** Bayesian priors help where OBG is currently unreliable (F6.3).
- **Natural conditional reasoning.** "Agent A believes X given context Y, Agent B believes ~X given context Z" — these aren't contradictions, and a PGM expresses that directly. DSPy currently catches this at Level 5 with a CoT prompt.
- **Research publication material.** Genuinely novel applied to multi-agent estate coherence. Strategic note in your memory points at this as Tier 2 research.

### Negative impact / risk

- **6-month rebuild minimum.** Touches OBG, the entire funnel, the resolution agent. Effectively a v2 architecture.
- **Performance regression risk.** Bayesian inference is slower than centroid math. Sub-millisecond Level 0 becomes tens of ms or more.
- **Hard to explain.** Customer engineers can read "cosine distance > 0.35." "Posterior probability of incompatibility > 0.7 under model M" is opaque.
- **Tooling immaturity.** No good off-the-shelf libraries for the specific shape we'd need. Lots of custom infrastructure.

### Effort

3–6 months. Genuine architecture rebuild. **Hold until post-Series-A and after first published systems paper.**

---

## 8. Recommended sequence

| Order | Structure | Why now (or not) |
|---|---|---|
| 1 | **Belief Disagreement Graph (BDG)** | Half-sprint, high pitch value, materializes work already happening |
| 2 | **Contradiction hypergraph** | Honest representation of N-way disagreement, reduces alert fatigue (F8.3), enables better resolution math |
| 3 | **Session/conversation DAG** | Opportunistic — build if a design partner mentions single-agent self-contradiction as a pain |
| 4 | **Semantic clustering** | After 1+ design partner has run for ~1 month and canonical vocabulary has stabilized |
| 5 | **Agent agreement profile** | Needs ~3 months of real production data; do it after second design partner |
| 6 | **Probabilistic graphical model** | Tier 2 research; pair with the systems paper, not before |

Rule of thumb: structures that improve the **pitch and demo** come first (BDG, hypergraph). Structures that improve **precision under production load** come second (clustering, agreement profile). Structures that improve **theoretical soundness** come last (PGM).

## 9. What NOT to do

- **Don't build any of these before the NeuralCraft pitch.** Same build-before-listening risk as everything else.
- **Don't promise PGM in customer conversations.** It's a research bet, not a deliverable.
- **Don't replace OBG centroids.** All six structures coexist with OBG, they don't replace it. The centroid math is fast and works.
- **Don't ship BDG without dashboarding it.** The whole pitch value is visibility; an unrendered BDG is just write amplification.

---

**End of design memo.** Revisit after first design partner engagement to re-rank based on real customer pain.
