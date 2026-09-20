# R194 HANDOFF — Hardening + Composition Closure (non-architectural)

## 1. Authority
Operator "APPROVE R194. Execute R194 exactly as proposed." on the closure-audit Part 12 proposal. Declared in `60_DECISION_LOG.md` R194-DEC-01 BEFORE any production commit. Baseline `main b5c46561`.

## 2. Boundaries
Additive. Reuse ONLY: the existing admission/principal resolver, `error_response`/`unauthenticated`, `Worker`, `OutboxRelay`, `WEBHOOK_STREAM`, `WebhookDeliveryHandler`, `stage_execution_event`, `ExecutionMessageHandler(outbox=, subscriptions=)`, `create_app(webhook_subscriptions=)`, `httpx` at the composition root. No new route, registry, engine, trust or credential system. Core untouched. UI trees frozen (CSP chosen to fit them as they are).

## 3. Slice
`round_r194` ceiling 3: `apps/api/app.py` (R194-A), `apps/composition/runtime.py` + `apps/main.py` (R194-B). N-5 checkpoints WITHDRAWN by finding R194-F1 (see DEC-01) — operator decision at closure.

## 4. Proof plan
RED `tests/security/test_r194_security_headers.py` + `tests/composition/test_r194_webhook_delivery.py` → implement → GREEN → regression → freeze `--check` → fresh-clone gate + gateway → PR (merge commit) → post-merge gate → DEC-02 → STOP.

## 5. Stop conditions
Fourth production file → STOP. Any `served_routes_v1` delta or contract SHAPE change → STOP + proposal. Freeze re-derive not MATCHES → STOP. Any need to touch `ui/` for CSP → STOP (would be a UI-thaw decision). Any need for a new port/abstraction to drive two workers → STOP.

## 6. Ledger
`evidence/r194_state_ledger.md`.

## 7. Closure (2026-09-20)
- **Result:** R194 CLOSED (R194-DEC-02). PR #46 merged by merge commit → `main 4f494344`; records-only closure PR follows.
- **Production:** 3/3 files (`apps/api/app.py`, `apps/composition/runtime.py`, `apps/main.py`); Core untouched; freeze `--check` MATCHES.
- **Gates:** gate of record 141eb531 PASS 3852/0/0/64 + gateway 194; post-merge 4f494344 PASS 3852/0/0/64 + gateway 194; `min_passed` 3837 → 3852.
- **Operating:** `OPENAPI_PUBLIC` (unset ⇒ public in-memory / gated durable), `HSTS=1` when TLS-terminated, `WEBHOOK_TIMEOUT_SECONDS` (10). Registered webhooks are now delivered by the `webhook-worker` lifespan task.
- **Withdrawn:** N-5 checkpoints (finding R194-F1) — operator decision.
- **Next:** STOP on main at the operator decision gate (N-5 path, AD-1, AD-2, AD-3, AD-5, P-R192-02, DEC-03/AD-6, AD-7, D-03 rotation).
