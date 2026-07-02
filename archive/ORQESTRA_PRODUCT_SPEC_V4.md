# Orqestra — Product Specification v4.0
## The Platform Pivot: Coherence Control Plane for Agentic AI

**Product:** Orqestra — AI Estate Coherence Infrastructure & Agent Control Plane
**Version:** 4.0 — Supersedes v3.x. Extends the SCCG/OBG/Canon foundation into a multi-agent control plane.
**Status:** Spec-ready. Codebase integration pending.
**Stack (unchanged):** FastAPI · PostgreSQL + pgvector · Redis + Celery · Docker Compose · React 19 + Vite + Tailwind 4
**Model stack (no exceptions):** `gpt-5.4-mini` for all LLM tasks · `text-embedding-3-small` (1536-dim) for all embeddings · DeBERTa-v3 local NLI. No Gemini, no Anthropic Claude, no other providers.

---

## 0. What Changed From v3 — Read This First

v3 was a coherence layer that sat **beside** someone else's agents. It observed claims, detected contradictions, traced causality. It hit a ceiling: detection alone is replicable, agents never queried Orqestra before acting, and it stayed optional tooling a buyer could rip out without anything breaking.

v4 resolves that ceiling not by making detection perfect, but by **reducing how much detection has to carry** — through three moves that turned out to be one strategy seen from three angles:

1. **Agent-builder** — Orqestra becomes the place agents are *authored*, on top of an existing framework (LangGraph first). Because we author the agent, we author the claim contract. Cleaner claims in → cleaner contradictions out. The newest capability fixes the oldest wound (detection ceiling).
2. **Canon (scoped + subscription)** — ground truth so detection is no longer the sole arbiter. Now with a concrete isolation and sharing model.
3. **LLM-escalation + opt-in training harvest** — the principled fallback for cases even well-shaped claims can't resolve, feeding a learning loop that improves detection on real traffic.

These form a closed pipeline:

```
Author clean agents (builder)
   → agents emit well-shaped claims
      → detection works better
         → Canon arbitrates ground truth (on the agent path)
            → residual hard cases escalate to LLM
               → harvested (opt-in) → train → detection improves on real traffic
```

**What Orqestra is NOT becoming:** an ADK or an orchestration framework. We do not compete with LangGraph/CrewAi/AutoGen. We are the **control plane over** whatever framework the market standardizes on. Orchestration is the on-ramp; coherence + Canon + estate-health is the product and the lock-in.

---

## 1. Product Thesis

Enterprises and AI-service providers run fleets of agents built on different frameworks at different times. Each agent independently accumulates its own model of reality. Nothing ensures they agree. Existing LLMOps tools (Arize, Langfuse, Braintrust, LangSmith) evaluate systems in isolation — they cannot see the contradiction that lives *between* agents.

Orqestra is the cross-system coherence layer **plus** a control plane to author, wire, run-monitor, and ground a fleet of agents — so the fleet stays coherent, accountable, and grounded against a canonical memory.

**Strategic arc:** Monitor → Canon → Context → OS. Canon is the inflection point where Orqestra becomes load-bearing infrastructure rather than optional tooling. The agent-builder is the mechanism that gets real multi-agent traffic flowing through Orqestra by default, which is what Canon needs and could not previously get.

---

## 2. The Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  AUTHORING LAYER  (the on-ramp / the data funnel)            │
│  Drag-and-drop builder · tool wiring · prompt config ·       │
│  character/persona · internal claim-shape specification      │
│  Compiles to → LangGraph (framework #1)                      │
├─────────────────────────────────────────────────────────────┤
│  ADAPTER / NORMALIZATION LAYER  (the hard IP)                │
│  Normalizes framework-native execution into ONE uniform      │
│  claim / interaction / lineage model → SCCG target schema    │
│  Execution runs on the CLIENT's infra. We observe + inject,  │
│  we do NOT host execution.                                   │
├─────────────────────────────────────────────────────────────┤
│  COHERENCE LAYER  (the product / the moat — already built)   │
│  SCCG · OBG · 5-level detection funnel · blast radius ·      │
│  LCA · causal lineage · Resolution Agent                     │
├─────────────────────────────────────────────────────────────┤
│  CANON LAYER  (load-bearing memory — write-back path)        │
│  Subscription Canon · scoped + shared stores · pre-action    │
│  query injection · fail-closed company isolation             │
├─────────────────────────────────────────────────────────────┤
│  LEARNING LAYER  (the improvement loop)                      │
│  LLM-escalation on low-confidence detection · opt-in,        │
│  scrubbed, revocable training harvest                        │
└─────────────────────────────────────────────────────────────┘
```

**Where IP concentrates:** the adapter/normalization layer. A competitor can wrap LangGraph in a weekend. They cannot wrap it *into a contradiction-detecting canonical graph* without having already built the coherence model that defines the target schema.

**Discipline rule:** every authoring/orchestration feature must exist *only to feed the coherence layer*. Tool-granting, character config, agent spawning earn their place by generating the claims, interactions, and lineage that make estate-health and Canon valuable. If a feature does not feed coherence, it is someone else's job.

---

## 3. Hosting & Execution Model

**Orqestra does not host agent execution.** Clients run agents on infra they already pay for and have set up.

- **Authoring** happens through Orqestra's frontend → compiles to LangGraph definitions.
- **Execution** happens on the client's infrastructure.
- **Observation** flows back to Orqestra via the adapter (claims, tool calls, interactions, lineage).
- **Injection** (Canon pre-action lookups) is the one active hook into the client's runtime.

Consequences: no hosting/scaling/cost surface on our side; we never compete with infra the client already owns; observation fidelity depends on the adapter capturing execution faithfully (this is the adapter's core responsibility).

---

## 4. Framework Choice — LangGraph First

Single framework first. The adapter normalization is the hard IP; prove it end-to-end on one engine before generalizing.

Selection criterion is **not** "best agent framework" — it is "which framework leaks the most observable structure into our graph with the least adapter pain."

**LangGraph wins:**
- Graph-native execution (explicit nodes/edges, state passing) maps almost directly onto SCCG/lineage — parent-child claim relationships and interaction edges come close to for-free.
- Largest ecosystem/mindshare → one integration covers the most market.
- Callback/checkpoint hooks give clean instrumentation without monkey-patching.
- Cost: heaviest abstraction to learn; LangChain API churn.

**Runners-up:** CrewAi (more opinionated role/task/crew model maps cleanly to a drag-and-drop builder, but execution is less graph-explicit so lineage capture costs more adapter work). AutoGen (strong on multi-agent conversation = our interaction story, but shiftier abstractions, riskier base).

**Pre-commit spike (half-day):** confirm LangGraph's callback/checkpoint surface exposes cross-node state provenance — which output fed which downstream node — at the granularity SCCG needs, without us reconstructing it. If provenance is clean, LangGraph is decisive. If lossy, the CrewAi gap narrows.

---

## 5. Canon — Subscription Model Within Company Isolation

### 5.1 The boundary model

**Company is the hard isolation boundary.** Nothing — no query, no resolution, no consensus — ever crosses it. This is the tenant boundary (`org_id`). Two enforcement regimes, cleanly separated:

- **At the company boundary:** physical, fail-closed isolation. A Canon query without a valid `org_id` scope returns nothing, ever. This is the thing a security team audits. There is no universal Canon to leak *from*.
- **Inside the company:** flexible subscription Canon. Conflicts here are a feature (surface them), not a breach.

Nothing is universal **except** the training corpus (Section 6), which is a separately-governed, scrubbed, opt-in export — never live Canon.

### 5.2 Subscription Canon (within the company)

Canon is **not** two fixed tiers. It is a set of scoped canon stores that systems/agent-sets **subscribe** to. "Shared" and "scoped" are degenerate cases of subscription:

- **Shared** = a store everyone in the company is auto-subscribed to, at lowest precedence.
- **Scoped** = a store with limited subscription, at higher precedence.

A system's effective Canon = the union of every store it subscribes to, resolved by precedence. This is the same mechanism as the context-package subscription thesis applied to ground truth — the two collapse into one primitive.

Granularity of stores: company-wide, per-system, or per-agent-set.

### 5.3 Data model

- **Canon stores** are first-class: `store_id` + owner scope (`org_id`, optional `system_id`).
- A system holds an **ordered list of subscriptions**: `(store_id, precedence_rank)`.
- `canonical_entities` and the canon store gain a **scope column**: `system_id` (nullable) + `org_id` (required).
- `/canon/resolve` and `/canon/list` take a **mandatory scope param** and **fail closed** without it. Scope is a wall the query physically cannot cross, not a filter applied after lookup.

### 5.4 Resolution order

```
Walk subscribed stores in precedence order (rank ascending = higher priority first)
   → first definitive match wins
   → never fall through to global (there is no global)
   → no match across all subscribed stores → fail closed (return nothing)
```

Day-one default: every system gets **one private store**, subscribed to nothing else. Looks exactly like simple scoped Canon. The subscription machinery is present but invisible until a customer runs a second system that genuinely needs to share facts. Do not build the hierarchy before someone needs the second floor.

### 5.5 Conflict between subscribed stores — BOTH, by design

When two subscribed stores disagree (store X says max HR 180, store Y says 165, system subscribes to both):

- **Precedence decides what the agent is served right now.** Deterministic, fast, cannot block the agent — higher-ranked store wins.
- **The conflict is simultaneously logged as a cross-store contradiction** in the dashboard for a human to reconcile.

The agent never stalls; the conflict never hides. This is the core Orqestra philosophy applied to Canon itself.

### 5.6 Canon epistemics (unchanged, locked)

- Consensus-derived values are **never** served to agents — only human-declared canonical values reach the agent path. Ten agreeing agents can all be wrong if they share a common source; consensus measures correlation, not correctness.
- Consensus appears exclusively in the dashboard as promotion candidates, **scoped the same way as stores** — consensus within a store/system, never pooled across systems (pooling silently recreates the universal-canon problem).
- Canon DB populated exclusively by human declaration: promote a candidate, manual declaration, or bulk import.

---

## 6. Learning Layer — Escalation & Opt-In Training

### 6.1 LLM escalation as a visible feature

When a hard case exceeds detection confidence, it escalates to `gpt-5.4-mini`. This is surfaced as a product feature, not a hidden patch: "Orqestra knows what it doesn't know, escalates, and learns." The original detection ceiling becomes a selling point — the system has a principled fallback and a learning loop.

### 6.2 Recommendation / prescriptive claims (already handled)

Recommendation-type claims are classified and parked as **neutral** — they do not bloat contradiction counts. Open consideration: genuinely-conflicting prescriptive claims (FitnessAgent says push, MedicalAgent says rest, one operating on stale canonical input) can disappear into the neutral bucket. Future work: a discriminator that surfaces the prescriptive conflicts that *matter* (those traceable to wrong/stale Canon) while keeping the rest neutral. Not v4-blocking.

### 6.3 Opt-in training harvest

The **only** path that crosses the company isolation wall. Rules:

- **Opt-in as default.** Train only if the company explicitly turns it on. "Your data never trains anything unless you explicitly enable it" — clean sentence a security team accepts. We trade corpus volume for trust, consistent with the isolation thesis.
- **Tiered consent:**
  - *Structural / metadata-level* — graph shapes, contradiction types, no payloads. Most companies will accept this; it is often the most valuable data for improving detection.
  - *Content-level* — actual claims. Far fewer will accept; may rarely be needed.
- **Always through the scrubbed projection.** Consent is permission, not a bypass. Even opted-in data flows through a sanitized projection, never a direct read from live Canon. Keeps "we read from a scrubbed export, never your live ground truth" true for everyone.
- **Cleanly revocable, and provably so.** Revoke must exclude already-ingested data from future training runs. Requires data lineage on the training corpus + exclusion-on-revoke. (Flag as fault-registry item — do not discover this during a security review.)

---

## 7. The Multi-Sided Market (open, must resolve)

A service-provider platform has at least two parties: the **provider** (builds/runs agents) and *their* **client** (whose work the agents do). Currently the whole mental model is the provider; the client side is blank. Decisions still needed:

- Who is the buyer?
- Who sees the estate-health dashboard — the provider, or is it white-labeled to their client?
- Does the client ever touch Canon?

This shapes pricing, the dashboard, and what "estate" means. Not v4-blocking but must be answered before the platform sales motion.

---

## 8. Re-Weighted Fault Registry

The platform pivot does not add a feature layer on top of v3 — it **re-weights the existing fault registry.** Items correctly deferred as single-tenant-pitch concerns become first-order platform concerns.

| Fault | v3 status | v4 status | Why it moved |
|---|---|---|---|
| F7.1.A — read endpoints not org-scoped | Low (single-tenant) | **Critical / blocking** | Multi-tenant Canon: one cross-company leak kills the product. Becomes the fail-closed company wall. |
| SDK `_telemetry_logger` singleton | Deferred (demo-only) | **Critical / blocking** | Many agents per provider, shared processes → multi-agent-per-process is now the default case, not the edge. Identity integrity is foundational. |
| F7.1.B — async `verify_api_key` wraps sync session | Deferred | **High** | Platform load surfaces event-loop blocking under sustained traffic. |
| F5.1 — circuit breaker open | Deferred | **High (procurement blocker)** | Platform sales motion → buyer security teams read the fault registry. |
| F8.1 — canary monitoring open | Deferred | **High (procurement blocker)** | Same. |
| F7.1.C — multi-process Prometheus metrics | Deferred | Medium | Cost visibility matters more when cost model owner flips (Section 9). |
| Training-corpus revocation lineage | New | **High** | Required for the opt-in revoke promise (Section 6.3). |

**Pattern:** half the "low-risk, deferred" v3 items are now "high-risk, blocking." Trust direction inverted — beside-the-stack we observed data clients already trusted; as a platform, providers trust *us* with their clients' agents and ground truth.

---

## 9. Cost Model (open)

Beside-the-stack, $0.19/1K samples was *our* cost to swallow. As a platform, whose budget pays for claim extraction when a provider runs a million samples?

- If **ours**: the GLiNER / fine-tuned DeBERTa / Phi-3-mini / Qwen-2.5-1.5B cost-reduction path ($0.19 → under $0.05, targeting the ~80%-of-cost claim-extraction step) moves from optimization to unit-economics survival.
- If **passed through**: a pricing decision not yet made.

Decide before the platform sales motion.

---

## 10. The Critical Unresolved Path — Write-Back

**This is the one thing that decides whether v4 reaches the agent path or stays observation.**

Observation (capturing claims) is passive and easy. Write-back — a LangGraph agent querying Canon *before* it acts — is an active injection into the client's runtime. If we cannot cleanly inject a Canon lookup into the execution loop, Orqestra stays a monitor forever — the exact ceiling this whole pivot exists to break.

Because we author the agent through the builder, we have the injection point the v3 beside-the-stack model lacked: we can bake a pre-answer Canon lookup into the authored agent's graph.

---

## 11. Immediate Next Step — The Fitness Demo Loop Spike

Do not pivot the demo. Extend the existing fitness agent system through the loop now assembled.

**The spike (pass/fail, closes the loop in practice or only on paper):**

1. **Author one fitness agent through the builder, on LangGraph,** with the internal claim-shape spec baked in.
2. **Inject one pre-answer Canon lookup** — e.g. MedicalAgent checks canonical max-HR before advising.
3. **Run one known contradiction scenario** from the existing demo set.
4. **Observe:** does the claim come out cleaner (detection relieved)? Does the Canon query land on the agent path before the answer?

**Pass =** authored agent emits well-shaped claim AND hits Canon pre-answer AND the known contradiction fires cleaner than the v3 baseline. That single spike validates the entire thesis end-to-end: authored agent → clean claims → Canon on the agent path → detection relieved → fallback to LLM → harvest to train.

**If write-back fails** (authored agent cannot hit Canon pre-answer), then write-back is the only thing to work next — everything else is hardening.

Demo framing stays the same vehicle:
- Canon scoped to this one company/system = the day-one default of the subscription model (one company, one system, one private store). Proves isolation without building the subscription machinery.
- LLM-escalation wired as a *visible* fallback, not a hidden patch.

---

## 12. Decision Log (resolved this cycle)

| Question | Decision |
|---|---|
| Build our own ADK? | No. Control plane over existing frameworks. ADK deferred indefinitely; justified only by a coherence requirement no framework can meet. |
| Host execution? | No. Runs on client infra. We observe + inject. |
| How many frameworks first? | One. LangGraph (pending provenance spike). |
| Canon universal? | No. Company is the hard isolation boundary. |
| Canon sharing model? | Subscription within company. Shared/scoped are degenerate cases. |
| Cross-store conflict resolution? | Both: precedence serves the agent, contradiction surfaces to humans. |
| Training data default? | Opt-in, tiered (structural vs. content), scrubbed projection, revocable. |
| Day-one Canon shape? | One private store per system; subscription machinery present but invisible. |

## 13. Still Open

- Write-back injection mechanics (Section 10) — **the** blocker to validate.
- Multi-sided market: buyer, dashboard ownership, client Canon access (Section 7).
- Cost model owner (Section 9).
- Company-level shared store: ship system-only first, add inheritance when a real customer has two systems that must share facts.
- Prescriptive-conflict discriminator (Section 6.2).

---

*Orqestra Product Specification — v4.0*
*Supersedes v3.x*
*Pivot: coherence layer → coherence control plane*
*Pipeline: author clean agents → well-shaped claims → detection relieved → Canon on agent path → escalate residual → opt-in harvest → improve*
*Model stack: gpt-5.4-mini (all LLM) · text-embedding-3-small 1536-dim (all embeddings) · DeBERTa-v3 (NLI local)*
