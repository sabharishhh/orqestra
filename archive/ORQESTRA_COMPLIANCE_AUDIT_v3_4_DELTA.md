# ORQESTRA Compliance Audit — v3.4.0 Delta

**Supplements:** `ORQESTRA_COMPLIANCE_AUDIT_v3_3.md`
**Sprint covered:** 7.1 (Observability & Metrics)
**Date:** 2026-06-28

This document records what Sprint 7.1 changed against the v3.3 audit and registers four new faults surfaced during instrumentation. The body of the v3.3 audit (layer scores, blocking-fault status for F1–F8 series, prioritized fix order) is unchanged except where noted below.

---

## 1. Sprint 7.1 — closures

The "logging and observability" gap noted as a recurring footnote across multiple layer assessments in v3.3 is now closed. Specifically:

- **Structured logging** — `structlog` with JSON output in prod, ConsoleRenderer in dev. Single chokepoint at `observability/configure_logging()`. Zero `logging.getLogger` calls remain outside the observability package.
- **Correlation ID** — pure-ASGI middleware reads/generates `X-Request-ID`, binds to contextvars, propagates through Celery via task headers. A single request_id traces from API receipt through every Celery task it triggers.
- **Tenant context** — every authed request emits log lines carrying `tenant_id` and `org_slug`. Multi-tenant log partitioning verified via `scripts/log_summary.py --org <slug>`.
- **Detection funnel timing** — all 5 levels (0, 1, 3, 4, 5) emit `detection.level.completed` with `duration_ms`, `outcome`, and candidate counts.
- **LLM + embedding call instrumentation** — every `gpt-5.4-mini` and `text-embedding-3-small` call routes through `services/llm_client.py` and `services/embed_client.py`, emits tokens + duration + estimated USD cost.
- **Endpoint DB timing** — `/canon/resolve`, `/canon/list`, `/contradictions/{id}/blast-radius`, `/contradictions/{id}/lineage-graph` emit `db.query` events with `query_name`, `duration_ms`, `row_count` per query.
- **Prometheus metrics** — opt-in via `ORQESTRA_METRICS_ENABLED=true`. Seven metric families exposed at `GET /metrics`.
- **Log replay** — `scripts/log_summary.py` produces a baseline table consumable as a pitch artifact.

This closes the observability footnote without re-opening any of the F1–F8 blocking-fault entries from v3.3.

---

## 2. Fault registry — new entries

### F7.1.A — Unauthenticated read endpoints are not tenant-scoped

**Surfaced by:** Sprint 7.1 made the asymmetry visible — every authed write log line carries `tenant_id` and `org_slug`; every unauth'd read line shows `null` for both.

**Affected endpoints:** `GET /contradictions/`, `GET /roi/summary`, `GET /graph/`, `GET /contradictions/{id}/blast-radius`, `GET /contradictions/{id}/lineage-graph`.

**Risk:** In a multi-tenant deployment, any reader sees all tenants' data. Currently masked because there is one customer (demo-fitness) and reads are dashboard-only. Becomes a real problem the moment a second tenant is onboarded.

**Severity:** High for production multi-tenant, low for current single-tenant pitch demo.

**Remediation:** Either add `verify_api_key` to read endpoints (matches write endpoints, breaks current public dashboard), or introduce session-based auth for the dashboard plus a session→org lookup. Architectural call — defer until first multi-tenant customer.

**Status:** Open. Documented for transparency in NeuralCraft pitch.

---

### F7.1.B — `verify_api_key` is async but wraps a sync SQLAlchemy session

**Surfaced by:** Sprint 7.1 — had to convert `verify_api_key` from sync to async so contextvar bindings would propagate to the route handler (sync dependencies run in a threadpool with isolated contextvars).

**Behavior:** The function is now `async def` but `db.query(System)...first()` and `system.organization.slug` inside it are sync DB calls that block the asyncio event loop.

**Risk:** At current scale (single-digit RPS), undetectable. At 100+ RPS, event loop blocking on auth queries will starve unrelated requests and inflate p99.

**Severity:** Low at current scale; medium-high at NeuralCraft customer scale.

**Remediation:** Either move auth back to sync and find another way to propagate tenant context (e.g. bind in middleware after reading and validating the bearer token there), or move to async SQLAlchemy. The first option is cheaper and lower-risk.

**Status:** Open. Will be surfaced quantitatively in Sprint 7.2 baseline.

---

### F7.1.C — Multi-process Prometheus metrics not aggregated

**Surfaced by:** Sprint 7.1 — `GET /metrics` is exposed on the api process. The four worker processes (extraction, default, dlq, beat) each maintain their own in-memory Prometheus registry that the api scrape endpoint cannot see.

**Behavior:** API-side metrics (HTTP duration, DB query duration on read endpoints) populate cleanly. LLM call duration and embedding call duration counters at the api `/metrics` endpoint show zero, because those calls happen in workers.

**Risk:** Pitch demo of `/metrics` understates the cost/throughput story by missing the LLM and embedding work that workers do.

**Severity:** Cosmetic for pitch; needs fixing before any production scraping setup.

**Remediation:** Standard `prometheus_client` multiprocess mode requires a shared directory and an env var (`PROMETHEUS_MULTIPROC_DIR`). Cleaner alternative: deploy Prometheus pushgateway, have workers push their metrics on a fixed cadence. Half-day of work either way.

**Status:** Open. Flagged in `PERFORMANCE_BASELINE.md` as known limitation.

---

### F7.1.D — DSPy apex judge token counts not captured

**Surfaced by:** Sprint 7.1 instrumentation — every other LLM call site routes through `services/llm_client.py` which captures `response.usage`. The Level 5 apex judge call uses DSPy's `apex_judge(...)` API, which owns the underlying OpenAI call and does not expose usage data through its return object in a stable way.

**Behavior:** Level 5 latency is timed correctly (via the `detection.level.completed` event). Token counts and per-call cost for apex judge invocations are missing from the cost aggregate.

**Risk:** Cost-per-claim reporting understates LLM spend by the apex judge's share. In the current baseline, apex judge fired once on the 9 candidates that entered Level 0, so the omission is small but non-zero.

**Severity:** Low for cost reporting; will grow as contradiction rates rise.

**Remediation:** Either (a) attach a custom DSPy `Callback` that logs usage from `lm.history`, or (b) replace the DSPy call with a direct `chat_completion(...)` through `services/llm_client.py` and reconstruct the chain-of-thought structure manually. Option (a) is cheaper and preserves the compiled DSPy weights.

**Status:** Open. Will revisit if NeuralCraft asks specifically for total LLM cost accounting.

---

## 3. Updated fault summary

| Fault | Source | Severity | Status after 7.1 |
|---|---|---|---|
| F5.1 — Circuit breaker missing | v3.3 audit | Medium-high | Open (unchanged) |
| F8.1 — Canary monitoring missing | v3.3 audit | Medium | Open (unchanged) |
| F7.1.A — Read endpoints not org-scoped | 7.1 (visibility), pre-existing | High in multi-tenant | Open, new entry |
| F7.1.B — Async auth wraps sync DB | 7.1 | Low-now / medium-soon | Open, new entry |
| F7.1.C — Multi-process metrics gap | 7.1 | Cosmetic | Open, new entry |
| F7.1.D — DSPy token counts uncaptured | 7.1 | Low | Open, new entry |

The 5 v3.3 blocking faults remain mitigated. The 6/8 pre-first-partner faults from v3.3 remain mitigated. Spec endpoint count unchanged at 14/21 (three missing: `GET /systems/{id}/score`, `PATCH /contradictions/{id}`, `PATCH /resolutions/{id}`).

---

## 4. Layer scores delta

Only one layer score changes versus v3.3:

- **Observability layer:** previously rated as a gap with no measurement infrastructure. Now: structured logging, correlation IDs, tenant context binding, per-stage timing, Prometheus metrics, log replay tooling. Reclassified as **production-ready for single-tenant**; multi-process aggregation (F7.1.C) is the remaining gap for full production.

All other layer scores from v3.3 (data, detection, resolution, API, frontend, infra, security) are unchanged.

---

## 5. Recommended sequence post Sprint 7.1

In priority order:

1. **NeuralCraft pitch.** Do not build further before listening.
2. **If load-test numbers are asked for:** Sprint 7.2 (load harness + sustained baseline). ~3 days.
3. **If first-partner conversation progresses:** Resolution Agent (the Canon→Gate transition). The single most strategic engineering deliverable in the next quarter.
4. **Defer until clear customer signal:**
   - F7.1.A (auth on reads): only when a second tenant is real.
   - F7.1.B (async auth): only when sustained load shows event-loop starvation.
   - F7.1.C (multi-process metrics): only when production monitoring is being set up.
   - F7.1.D (DSPy tokens): only if total LLM cost accounting becomes a stated requirement.
   - The three missing spec endpoints (`GET /systems/{id}/score`, the two PATCHes): only if a customer asks for the specific functionality.
   - Sprint 7.2 (load test): only if asked, or before paid pilot.

---

**End of v3.4.0 delta.** Next audit revision will fold these entries into the main `ORQESTRA_COMPLIANCE_AUDIT_v3_X.md` after the next significant feature sprint (likely Resolution Agent).
