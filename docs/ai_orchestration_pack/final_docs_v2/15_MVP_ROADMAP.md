# 15 — MVP Roadmap

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-011)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
NOTE: Legacy "state files / Git/state/handoff protocol" wording is explicitly
superseded by D10/D11 (single mutable state = PROJECT_EXECUTION_STATE.md).
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

---

## 1. MVP Philosophy

Build the smallest system that proves the architecture without overbuilding.

MVP must validate:

```text
unified API
provider abstraction
model registry
basic routing
execution records
memory basics
admin config basics
usage accounting
security boundaries
recovery protocol
```

---

## 2. MVP Scope

### Include

```text
Auth: email/password + verification
Tenant: personal tenant per user
API: POST /v1/execute + execution status
Provider framework: 1-2 providers
Model registry: static + admin editable
Router: simple policy + tier + explicit model
Execution: single + pipeline basics
Memory: conversation + user preference basics
Roles: system roles only
Skills: local approved skills only
Tools: GitHub read-only optional
Evaluation: basic deterministic + model judge
Usage: task units estimate/reserve/settle
Admin: users/plans/models/providers/routing basics
Observability: logs + traces + audit events
Recovery: Git/state/handoff protocol
```

### Exclude Initially

```text
full client runtime
terminal/local filesystem tools
automatic training promotion
complex workflow designer
multi-region active/active
Kafka
full skill marketplace
advanced billing payments integration
```

---

## 3. Phase 0 — Repo / Governance

Deliver:

```text
engineering protocol
implementation plan
ADR templates
state files
CI basic checks
```

Exit:

```text
repo initialized
first commit
state system works
```

---

## 4. Phase 1 — Contracts

Deliver:

```text
API schemas
core domain types
provider contract
model contract
execution contract
error contract
```

Exit:

```text
contract tests pass
schemas validated
```

---

## 5. Phase 2 — Identity / Tenant / Security

Deliver:

```text
user registration
email verification
login/session
personal tenant
basic RBAC/entitlements
capability firewall skeleton
```

Exit:

```text
auth tests pass
tenant isolation tests pass
```

---

## 6. Phase 3 — Storage / Observability

Deliver:

```text
PostgreSQL migrations
Redis setup
object storage abstraction
secret manager abstraction
basic audit logs
OpenTelemetry setup
```

---

## 7. Phase 4 — Provider + Model MVP

Deliver:

```text
provider registry
one provider adapter
model registry
provider-model binding
credential reference
health checks
```

---

## 8. Phase 5 — Routing + Execution MVP

Deliver:

```text
POST /v1/execute
router simple scoring
single execution
pipeline execution
execution status endpoint
usage reservation/settlement
```

---

## 9. Phase 6 — Context / Roles / Skills MVP

Deliver:

```text
conversation history
basic user preferences
system roles
local skills
context composer
```

---

## 10. Phase 7 — Evaluation + Admin MVP

Deliver:

```text
basic evaluation policy
model judge optional
admin models/providers/plans/routing
learning dashboard placeholder
```

---

## 11. Phase 8 — Hardening

Deliver:

```text
security tests
provider failure tests
rate limit tests
queue/retry tests
secret redaction tests
load smoke tests
```

---

## 12. MVP Definition of Done

```text
API can execute a request end-to-end.
At least one provider works through adapter contract.
Router chooses model/provider via policy.
Execution is recorded and recoverable.
Usage is reserved and settled.
Basic evaluation record exists.
Admin can enable/disable model/provider and adjust plan.
Tenant isolation tests pass.
No secrets in logs.
Every phase committed and documented.
```

---

## 13. If No Real AI Providers Exist Yet

The MVP may begin with provider scaffolding only if real provider details are not ready.

Allowed:

```text
Provider contracts
Provider registry
Manifest schema
Common provider errors/capabilities
Disabled diverse provider templates
Scaffold validation tests
Pending real providers list
```

Forbidden:

```text
Fake working providers
Invented credentials
Invented live model names
Templates marked active
Provider-specific shortcuts inside Core
```

Use:

```text
23_AI_PROVIDERS_SCAFFOLDING_POLICY.md
```

End-to-end AI execution is not considered complete until at least one real provider is implemented and verified.
