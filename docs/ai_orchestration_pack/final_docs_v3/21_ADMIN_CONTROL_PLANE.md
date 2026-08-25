# 21 — Admin Control Plane
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-009
SUPERSEDES:
  final_docs_v2/11_ADMIN_CONTROL_PLANE_SPEC.md
MIGRATION_TYPE: CARRY (verbatim)
DECISION_PRESERVATION: Admin modules, configuration lifecycle, control
matrix, plan configuration, routing policy configuration, learning
dashboard, admin audit, required admin tests, model control administration,
and provider-agent (single and multi) administration carried unchanged.
No decision changed.
RELATED_AUTHORITY:
  Routing policies administered here: final_docs_v3/11_MODEL_ROUTING_AND_MODEL_CONTROL.md
  Provider/account administration:    final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md
```

---

## 1. Purpose

Admin Control Plane manages configuration and policies without changing Core code.

Everything configurable must be:

```text
versioned
validated
previewable
audited
rollbackable
```

---

## 2. Admin Modules

```text
Overview
Users
Tenants
Plans
Providers
Provider Accounts
User Credentials Policy
Models
Model Tiers
Routing Policies
Execution Policies
Roles
Skills
Tools
Evaluation
Learning
Security
Audit
Observability
Feature Flags
System Settings
```

---

## 3. Configuration Lifecycle

```text
Draft
↓
Validate
↓
Preview Impact
↓
Publish
↓
Observe
↓
Rollback if needed
```

---

## 4. Control Matrix

| Area | Admin Can Control | Admin Cannot Break |
|---|---|---|
| Models | enable/disable, tier, weights | model/core separation |
| Providers | enable/disable, accounts, priority | provider/core boundary |
| Routing | weights, fallback, tiers | deny-by-default security |
| Plans | units, entitlements, limits | accounting integrity |
| Skills | import, approve, disable | scan/review requirement |
| Tools | enable, permissions, approval rules | capability firewall |
| Learning | datasets, teacher policy, canary | eligibility/verification requirement |
| Security | rate limits, detection thresholds | tenant isolation, crypto, secrets |
| Evaluation | thresholds, graders visibility | evidence integrity |
| Observability | sampling and retention | security audit integrity |

---

## 5. Plan Configuration

```yaml
plan: pro
limits:
  task_units: 100
  image_generations: 20
  max_parallel_executions: 3
entitlements:
  models:
    max: false
    medium: true
  tools:
    github_read: true
    github_write: false
  agent_mode: true
```

---

## 6. Routing Policy Configuration

```yaml
routing_policy: default_v1
weights:
  quality: 0.35
  reliability: 0.20
  cost: 0.15
  latency: 0.15
  context_fit: 0.10
  policy_preference: 0.05
fallback:
  explicit_model: same_model_different_provider
  auto: same_tier
```

---

## 7. Learning Dashboard

Admin sees:

```text
verified samples
gold samples
dataset coverage
task coverage
specialist models
accuracy trends
cost reduction
teacher agreement
canary status
promotion history
rollback actions
```

User feedback visibility is admin-controlled.

---

## 8. Admin Audit

Every published config change records:

```text
who
what
previous version
new version
validation result
impact preview
timestamp
rollback target
```

---

## 9. Required Admin Tests

```text
config draft validation
publish creates version
rollback restores previous version
invalid policy rejected
security invariant cannot be disabled
plan change affects eligibility
routing policy version used in execution snapshot
admin action audited
```

---

## 10. Model Control Administration

Admin must have full control over what level of model selection is available to users, plans, API keys, and projects.

---

### 10.1 Model Control Levels

```text
AUTO_ONLY
TIER_SELECTION
EXPLICIT_MODEL
EXPLICIT_MODELS
AGENT_NODE_MAPPING
PROVIDER_SELECTION
```

Example plan configuration:

```yaml
plan: pro
model_control:
  auto: true
  tier_selection: true
  explicit_model: true
  explicit_models: false
  agent_node_mapping: false
  provider_selection: false
  max_parallel_models: 1
  allowed_tiers:
    - fast
    - medium
  denied_models: []
```

Advanced plan:

```yaml
plan: enterprise
model_control:
  auto: true
  tier_selection: true
  explicit_model: true
  explicit_models: true
  agent_node_mapping: true
  provider_selection: true
  max_parallel_models: 5
  allowed_strategies:
    - fallback_chain
    - parallel_compare
    - debate
    - specialist_roles
```

---

### 10.2 Admin Controls

Admin can configure:

```text
which models are visible
which tiers are visible
which plans can choose explicit models
which plans can select multiple models
which plans can map models per Agent node
which strategies are allowed
maximum parallel model count
which models can be judge models
whether provider selection is allowed
fallback policy defaults
cost budget limits for multi-model execution
```

---

### 10.3 Safety Constraints

Admin cannot allow model control to bypass:

```text
tenant isolation
entitlements
credential boundaries
provider/account health checks
secret handling
capability firewall
usage accounting
audit logging
```

---

### 10.4 UI Recommendation

Expose model control progressively:

```text
Basic users:
- Auto
- Fast / Medium / Max

Advanced users:
- Choose model
- Choose fallback behavior

Enterprise/API users:
- Choose multiple models
- Parallel compare
- Debate
- Per-agent-node model mapping
- Optional provider selection
```

---

### 10.5 Required Admin Tests

```text
plan allows explicit model
plan denies explicit model
plan denies multiple models
admin hides model from user
max parallel model limit enforced
provider selection disabled
judge model restricted
agent node mapping allowed only for permitted plan
model control changes versioned and audited
```

---

## 11. Provider-Agent Model Administration

Admin must be able to control whether provider-agent models are visible and usable.

Controls:

```yaml
provider_agent_control:
  enabled: true
  allowed_plans:
    - enterprise
  allow_provider_managed_state: true
  allow_provider_side_tools: false
  require_trace_visibility: true
  require_evaluation: true
  max_runtime_seconds: 900
  max_cost_units: 10
```

Admin can configure:

```text
which provider-agent models are enabled
which plans/users can use them
whether provider-side tools are allowed
whether provider-managed state is allowed
required evaluation policy
runtime/cost limits
fallback behavior if provider-agent fails
```

Security invariants still apply.

---

## 12. Multi Provider-Agent Administration

Admin must be able to control provider-native agents separately from normal models.

Controls:

```yaml
multi_provider_agent_control:
  enabled: true
  allowed_plans:
    - enterprise
  max_provider_agents_per_execution: 3
  allowed_strategies:
    - provider_agent_pipeline
    - provider_agent_parallel_compare
    - provider_agent_specialist_roles
  allow_provider_side_tools: false
  require_platform_evaluation: true
  fallback_to_platform_native_workflow: true
```

Admin can enable/disable individual provider agents, not only whole providers.

Example:

```text
Provider X chat model: enabled
Provider X code agent: enabled for enterprise only
Provider X autonomous browser agent: disabled
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–12 (purpose, admin modules, configuration lifecycle, control matrix, plan configuration, routing policy configuration, learning dashboard, admin audit, admin tests, model control administration, provider-agent model administration, multi provider-agent administration) | v2 11 §1–12, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header and this
traceability section were added. No admin control or policy rule was modified.
