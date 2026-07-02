# Orqestra — v4 Fault Triage & Build Order
## Reasoned over the full fault registry, re-weighted for the platform pivot

**Purpose:** Decide, per fault, what must be built into the v4 system *now* vs. what is acceptable to leave open during the MVP/demo phase. The MVP-acceptable list (Section 4) is the one to consult during a sprint when something doesn't resolve cleanly and you're deciding whether to fix it or save time.

**Key principle carried from the v4 pivot:** the platform model re-weights the registry. Half the items that were "low-risk, deferred" under the single-tenant beside-the-stack model become "high-risk, blocking" the moment Orqestra hosts authored agents for providers whose security teams read this document. Isolation and identity move to the front; cosmetic and scale-only faults move back.

**How to read the tables:**
- **MUST** = build it in now. Skipping it produces silent wrong results, a trust-destroying moment, or a security hole.
- **SHOULD** = build before the first real design partner. Acceptable to skip for an internal/synthetic demo only.
- **MVP-OK** = acceptable to leave open through the demo/MVP phase. Revisit only if it actually bites. This is your time-saving list.

---

## 1. The Re-Weighting — What Moved Because of v4

These are the faults whose priority changed *specifically because* of the platform pivot. Everything else keeps roughly its v3 weight.

| Fault | v3 weight | v4 weight | Reason it moved |
|---|---|---|---|
| F7.1.A — read endpoints not org-scoped | Low (single-tenant) | **BLOCKING** | Company is now the hard isolation wall. One cross-company Canon leak ends the product. This *is* the fail-closed boundary from the v4 spec §5.1. |
| SDK `_telemetry_logger` singleton | Deferred (demo-only) | **BLOCKING** | Many agents per provider in shared processes → multi-agent-per-process is the default, not the edge. Agent identity is the foundation the whole graph sits on. |
| F7.1.B — async `verify_api_key` wraps sync session | Deferred | **SHOULD** | Platform traffic surfaces event-loop blocking under sustained load. Tolerable for a single-tenant demo, not for a fleet. |
| F5.1 — circuit breaker open | Deferred | **SHOULD (procurement)** | Platform sales motion means buyer security teams read the registry. An open circuit breaker is a visible gap. |
| F8.1 — canary monitoring open | Deferred | **SHOULD (procurement)** | Same — "the monitor that can't tell if it's broken" reads badly in a security review. |
| Training-corpus revocation lineage | New | **SHOULD** | Required to honour the opt-in/revoke promise (v4 spec §6.3). Don't discover this during a security review. |
| F7.1.C — multi-process Prometheus metrics | Deferred | **MVP-OK** | Cost visibility matters more once the cost-model owner flips, but it's not blocking and the numbers are knowingly incomplete. |

**The pattern in one line:** isolation faults and identity faults graduate to blocking; everything cosmetic, scale-only, or cost-visibility stays deferrable.

---

## 2. MUST — Build Into v4 Now (non-negotiable)

These produce silent corruption, a trust-killing demo moment, or a security hole. None are skippable even for a synthetic demo.

### Core engine / correctness

| Fault | Why MUST | What "done" looks like |
|---|---|---|
| **F1.4** — contradiction pair order normalization | Duplicate alerts from day 1; breaks dashboard dedup and the ROI story. Cheap to fix. | `normalize_claim_pair()` called before every insert/dedup; DB check constraint; idempotency test passes. |
| **F1.6** — HNSW over IVFFlat | IVFFlat degrades silently under the dynamic data a live agent fleet produces. | Linter fails build on `ivfflat` in any migration. |
| **F2.4** — causal origin must be SCCG-grounded | Single most trust-destroying failure. A fabricated "where it came from" in the demo is fatal — this is your killer demo moment, it must be real. | `causal_origin_hypothesis` only ever derived from SCCG context; fallback string when data absent. |
| **F5.2** — OBG chains before detection | Race condition gives correct-looking but wrong funnel behaviour. Authoring clean agents is pointless if detection runs on stale belief state. | Celery `chain(update_belief_state, check_new_claim)` everywhere; no independent `.delay()` pair. |
| **F5.3** — dead letter queue | Contradictions silently vanish. In a demo, a disappeared contradiction is an unexplained blank panel. | DLQ configured; `on_failure` routes payload + reason; daily reader. |
| **F8.4 / 12.1** — SCCG append-only + write-validation trigger | The whole product is built on the SCCG being trustworthy causal ground truth. Corruption is undetectable from outside. | Append-only RLS policy; insert-validation trigger enforcing the three invariants. |

### v4-specific (platform isolation & identity)

| Fault | Why MUST | What "done" looks like |
|---|---|---|
| **F7.1.A → company isolation wall** | The v4 thesis is "your ground truth never leaves your boundary." A scope-less Canon read returning global results breaks the entire trust story and the sale. | `/canon/resolve` and `/canon/list` take a mandatory scope param and **fail closed** without it. Scope is a wall the query can't cross, not a post-filter. Test: scope-less read returns nothing. |
| **SDK singleton → per-agent identity** | Multi-agent-per-process is now default. A singleton telemetry logger overwrites agent identity, corrupting every claim's provenance — poisoning the graph at the source. | Telemetry/identity is instance-scoped, not module-global. Multi-agent-in-one-process test asserts distinct identities. |
| **Canon epistemics: consensus never on agent path** | Locked architecture. Consensus is correlation, not correctness. Serving consensus to agents silently recreates the universal-canon failure. | Only human-declared canonical values reach the agent path; consensus appears only as scoped dashboard promotion candidates. |
| **F2.4-adjacent: claim-shape contract at authoring** | The entire v4 detection-relief thesis depends on authored agents emitting well-shaped claims. If the builder doesn't impose the claim contract, the ceiling doesn't lift. | Builder bakes claim-shape spec into the authored LangGraph agent; factual vs. prescriptive tagged at emission. |

---

## 3. SHOULD — Build Before First Real Design Partner

Acceptable to skip for an **internal or synthetic demo only**. The moment a real provider/partner is on the system, these are required. Several are procurement-visible.

| Fault | Why SHOULD | Skip only if… |
|---|---|---|
| **F1.1** — vector clock bootstrap flood | Day-1 false-positive flood destroys first impression on a new system integration. | Demo uses pre-seeded agents past bootstrap. |
| **F1.2** — content hash normalization | Inflated metrics, duplicate alerts undermine the ROI number you pitch. | Demo claims are hand-controlled and won't paraphrase-collide. |
| **F1.3** — LCA recursive CTE depth cap | Crashes the DB at scale; LCA is a killer demo moment so it must not hang. | Demo DAGs are small (<500 nodes) — but add the `WHERE depth < 500` cap anyway, it's one line. |
| **F2.1** — cold-start visibility | Partner thinks the product is broken in week 1 when nothing's detected yet. | Synthetic demo always has contradictions present. |
| **F2.5** — regression detection | A resolved contradiction that silently recurs is the highest-risk credibility failure. | No resolution loop exercised in the demo. |
| **F5.1** — LLM circuit breaker | Dashboard breaks on every OpenAI outage; **procurement-visible**. Also gates the v4 escalation feature — escalation without a breaker is a retry-storm. | Demo runs offline / controlled API. But wire it before any partner. |
| **F8.1** — canary monitoring | "The monitor that can't tell if it's broken"; **procurement-visible**. | Internal demo where you manually verify detection. |
| **F9.2 / 12.14** — correction target is a URI | Vague targets make resolution proposals useless — and proposals are the product's claimed value. | Demo doesn't surface resolution proposals as a buy-reason. |
| **F7.1.B** — async `verify_api_key` blocking | Event-loop blocking under sustained fleet load. | Single-tenant demo with low concurrency. |
| **Training revocation lineage** | Needed to honour opt-in/revoke (v4 §6.3); **procurement-visible**. | Training harvest not enabled for any real company yet (it's opt-in default-off, so genuinely deferrable until first opt-in). |
| **F3.4** — PII scrubber per-vertical allowlist | Destroys the value prop in regulated verticals; required before any real (esp. clinical/finance) data. | Synthetic demo with no real PII. |
| **F7.1** — write-hook HMAC signing | API-key-only auth lets a leaked key poison the SCCG. Required before real write traffic. | Demo write path is internal/trusted only. |

---

## 4. MVP-OK — Acceptable to Leave Open Through the Demo/MVP Phase

**This is the time-saving list.** During a sprint, if one of these doesn't resolve cleanly, leave it — it won't break the demo, the isolation story, or the core thesis. Each row says *why it's safe to defer* and *the trigger that would force it back onto the board.*

| Fault | Safe to defer because… | Forces back onto the board when… |
|---|---|---|
| **F1.5** (and other scale-only SCCG edges not in §2) | Demo data volumes are tiny; corruption modes need months of high-frequency traffic. | First real partner runs sustained traffic. |
| **F2.2** — DeBERTa truncation on long claims | Affects clinical/legal accuracy at the margins; demo claims are short. | Expanding into long-document verticals. |
| **F2.3** — per-entity cosine thresholds | A single global threshold is fine for one well-understood demo vertical (fitness). | Second vertical with different semantic density (finance/legal). |
| **F3.1** — embedding model version pinning | `text-embedding-3-small` is stable and locked in the stack; silent-failure risk is real but low-probability near term. | Before any production partner — cheap to pin, do it then. |
| **F3.2** — domain-scoped fine-tuning | No fine-tuning data exists yet. Schema should be ready (per §11 of registry) but no build needed. | 50+ labeled examples accumulate in a domain. |
| **F4.1** — write-hook coverage estimation | Swarm-coverage verifiability matters for the *value claim*, not for the demo loop. | Pitching swarm coverage as a paid feature. |
| **F4.2** — SDK version compatibility | You control the demo environment; no host-app upgrade churn. | External teams install the SDK at their own pace. |
| **F4.4** — historical log out-of-order clocks | The v4 demo is live authored agents, not log ingestion. Path not exercised. | A customer onboards via log ingestion. |
| **F6.1** — entity induction second-pass merge | Ontology proliferation needs many entities over time; demo has a handful. | Entity count grows past manual manageability. |
| **F7.1.C** — multi-process Prometheus metric aggregation | Cost/metric numbers are knowingly incomplete; not blocking, not isolation-related. You already decided against a live-metrics frontend for exactly this reason. | Cost model flips to "ours" and unit economics need real per-worker numbers. |
| **F7.1.D** — DSPy apex judge token counts uncaptured | Framework limitation; affects cost accounting precision only. | Same trigger as F7.1.C — accurate cost accounting becomes load-bearing. |
| **F7.2** — auto-apply prompt-injection defense | Auto-apply is Phase 2+. v4 keeps corrections human-gated. Design the schema, don't build the check. | Any auto-apply mode is enabled. |
| **F7.3** — API keys in version control | Standing best practice (12.7) + `git secrets` scan covers it; the SDK warning is a nicety. | N/A — the CI scan is the real control; the SDK warning is genuinely optional. |
| **F8.2** — funnel efficiency masks detection failure | This is a *production monitoring* concern. In a demo you verify detection directly. | First partner relies on the funnel-efficiency metric unattended. |
| **F8.3** — proposal throttling (anti-fatigue) | Needs 200+ proposals to matter; no demo reaches that. | Sustained partner usage with a live resolution feed. |
| **F9.1 / 12.11** — demo vertical matching | You're already on the *right* vertical (fitness) for the current target. The rule matters, the *build* (FinTrack/SaaSTrack scenarios) doesn't yet. | Pitching a prospect in a different vertical. |
| **F9.3** — belief heatmap legibility at scale | 500-cell unreadable matrix needs 10×50; demo has far fewer. | Estate grows past ~10 systems × ~10 entities. |
| **F10.1** — synthetic injection for empty-window partners | The demo is synthetic by design; always has contradictions. | A real partner hits a 30-day empty window. |
| **F10.2** — managed-KB connectors (Notion/Confluence/Pinecone) | v4 demo doesn't depend on third-party KB write hooks. | Second partner cohort uses managed KBs. |

---

## 5. v4-Specific Open Items Not in the Original Registry

These come from the platform pivot and need a decision, but most are **MVP-OK to leave open** because they're answered by deferring the multi-sided/platform motion, not by code.

| Item | Status | Reason |
|---|---|---|
| **Write-back injection mechanics** (v4 §10) | **MUST-VALIDATE (spike, not fix)** | This decides whether v4 reaches the agent path or stays observation. It's not a "fault to fix" — it's the go/no-go spike (the fitness loop spike, v4 §11). Validate before committing the build. |
| Multi-sided market: buyer / dashboard ownership / client Canon access (§7) | **MVP-OK** | Answered by deferring the platform sales motion, not by code. Single demo = single party. |
| Cost-model owner (§9) | **MVP-OK** | No real billing in the demo. Decide before the platform sales motion. |
| Company-level shared store (vs system-only) | **MVP-OK** | Ship system-scoped only first (one private store per system). Add inheritance when a real customer runs two systems that must share facts. Don't build the second floor early. |
| Cross-store conflict: precedence + contradiction (§5.5) | **SHOULD** | Only relevant once a system subscribes to ≥2 stores. Day-one default is one store, so no conflict can arise — but design the resolution-walk so adding it later isn't a re-architecture. |
| Prescriptive-conflict discriminator (§6.2) | **MVP-OK** | Recommendation claims already park neutral. Surfacing the *ones that matter* is an enhancement, not a blocker. |

---

## 6. Sprint Decision Rule (the one-liner to keep on the board)

> If a fault is in §2 (MUST) — fix it, no exceptions.
> If it's in §3 (SHOULD) — fix it before a real partner touches the system; skip only for an internal/synthetic demo.
> If it's in §4 (MVP-OK) — **leave it open unless its "forces back" trigger has actually fired.** Saving the time is the correct call.

The two things you can never defer, restated because they're the v4 thesis itself:
1. **Company isolation fails closed** (F7.1.A → scope wall). No universal Canon to leak from.
2. **Agent identity is per-instance, never global** (SDK singleton). The graph is only as trustworthy as the identities at its source.

Everything else is negotiable against time.

---

*Orqestra v4 Fault Triage — derived from Fault Registry v1.0, re-weighted for the platform pivot*
*MUST / SHOULD / MVP-OK split is the sprint-time decision aid*
