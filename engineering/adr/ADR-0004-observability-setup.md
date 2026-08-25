# ADR-0004 — Observability Setup (OpenTelemetry + Structured Logging)

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-25: "ADR-0004 = ACCEPTED")
DATE: 2026-08-25
TASK: T-IMPL-017
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: MVP Phase 3 "OpenTelemetry setup" (41 §42) must not land — and no
observability dependency may be added to `pyproject.toml` — until this ADR
is ACCEPTED with explicit operator sign-off (PHASE_2_GOVERNANCE).

---

## Context

Fixed constraints (40 §5.3; 02 invariants; 20 §5):

```text
- Standard = OpenTelemetry. Not negotiable per 40 §5.3; the choice here is
  HOW to wire it, not whether.
- Data types = logs, metrics, traces, audit, execution records, evaluation
  evidence. Audit is ALREADY a core port (T-IMPL-014, append-only) — audit
  is NOT re-homed into telemetry; telemetry may reference audit event ids.
- Sampling = adaptive (normal → reduced; error/slow/high-value/debug →
  full). Sampler must be pluggable from day one.
- Secrets/credential material must never appear in logs/spans (20 §5);
  scrubbing is a boundary concern.
- Core purity: core/ must not import OTel SDK — instrumentation lives in
  apps/ + infrastructure/; core exposes at most a neutral tracing port if
  core-level spans are ever needed.
- Hermetic gates: verification must not need a collector; exporters must
  default to no-op/console in dev and test.
```

## Alternatives

### A. opentelemetry-python (API+SDK) + OTLP exporter + structlog for logs

Pros:
```text
- Canonical implementation of the mandated standard; auto-instrumentation
  packages exist for FastAPI, SQLAlchemy, redis, asyncpg — matching every
  binding chosen in ADR-0001/0002/0003.
- API/SDK split fits the boundary: the lightweight `opentelemetry-api` is
  importable by instrumented layers; the SDK + exporters are wired ONLY at
  app composition root (apps/), keeping vendor/back-end choice deferred.
- OTLP exporter is back-end-neutral (Jaeger/Tempo/Datadog/etc. all ingest
  OTLP) — no vendor decision needed now.
- structlog renders JSON logs with trace_id/span_id correlation via a
  processor; matches ADR-0001's sketch ("OpenTelemetry Python + structlog").
- Custom Sampler interface supports the 40 §5.3 adaptive policy
  (error/slow/high-value/debug → full) as a small local class.
```
Cons:
```text
- Several packages (api, sdk, exporter, per-library instrumentations) —
  dependency count grows; mitigated by pinning only what each phase uses.
- Python OTel logs-bridge is younger than traces/metrics; mitigated by
  keeping structlog as the log pipeline and correlating ids, not routing
  logs through OTel initially.
```

### B. Vendor SDK first (Sentry / Datadog / Elastic APM)

Pros:
```text
- Fast time-to-dashboard.
```
Cons:
```text
- Violates 40 §5.3 (standard = OpenTelemetry) as the foundation; vendor
  lock-in at the instrumentation layer; back-ends remain reachable from A
  via OTLP anyway.
```

### C. Minimal DIY (structlog only + custom middleware timings, add OTel later)

Pros:
```text
- Fewest dependencies now.
```
Cons:
```text
- Defers the mandated standard and bakes in ad-hoc span/metric shapes that
  must be ripped out; execution records and provider-call tracing (the
  platform's core value) need real traces early; retrofit cost exceeds the
  saved dependency weight.
```

## Decision

**Alternative A**, wired at the composition root:

```text
Packages:    opentelemetry-api, opentelemetry-sdk,
             opentelemetry-exporter-otlp-proto-http (deferred until a
             collector exists), per-library instrumentations added in the
             same phase as the library they instrument; structlog for logs
Wiring:      apps/ composition root configures TracerProvider/
             MeterProvider + resource attrs (service.name, tenant-safe
             attrs only); dev/test default = console/no-op exporters —
             gates stay hermetic
Sampling:    custom AdaptiveSampler implementing 40 §5.3 policy;
             ParentBased(root) composition; policy thresholds in config
Logs:        structlog JSON pipeline; processor injects trace_id/span_id;
             secret-scrubbing processor at the pipeline head (20 §5)
Boundary:    core/ must not import opentelemetry.* or structlog —
             import-linter contract lands WITH the dependency; if core
             spans become necessary, a neutral TracerPort is introduced
             then (own mini-decision, appended here if trivial)
Audit:       untouched — remains the append-only core port (T-IMPL-014);
             telemetry references audit ids, never duplicates content
```

## Reason

```text
- 40 §5.3 fixes the standard; A is its canonical implementation with the
  API/SDK split matching our boundary rules exactly.
- OTLP keeps the back-end decision open (no vendor ADR needed yet).
- B inverts the mandated layering; C delays the standard where retrofit is
  most expensive (execution/provider tracing).
- Consistent with ADR-0001's ACCEPTED sketch.
```

## Consequences

```text
+ Every later binding (FastAPI, SQLAlchemy, redis) gets tracing by adding
  its instrumentation package in the same task that adds the library.
- New deps: opentelemetry-api/sdk (+ structlog) — pinned ONLY after this
  ADR is ACCEPTED; exporter + instrumentations ride with their phases.
- Import-linter contract: core must not import opentelemetry/structlog.
- A back-end/collector choice becomes a small future decision (OTLP makes
  it low-stakes; DECISION_LOG entry unless it turns architectural).
Rollback: instrumentation is composition-root-only; removing/replacing the
SDK does not touch core or contracts.
```

## Status

ACCEPTED (T-IMPL-017, 2026-08-25) by explicit operator decision recorded in
PROJECT_EXECUTION_STATE.md: "Continue from the current checkpoint with the
operator authorization already granted: ADR-0004 = ACCEPTED". Alternative A
is confirmed as proposed, with no amendments. The observability
dependencies (opentelemetry-api/sdk, structlog), the 7th import-linter
contract, and the apps/ composition-root wiring are now unblocked. From
this point this file is append-only per ADR rules (40 §8.1); changes
require a superseding ADR.
