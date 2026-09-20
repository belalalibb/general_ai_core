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
