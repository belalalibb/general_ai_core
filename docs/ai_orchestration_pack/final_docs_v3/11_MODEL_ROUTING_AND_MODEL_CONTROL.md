# 11 — Model Routing and Model Control
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-007
SUPERSEDES:
  final_docs_v2/06_MODEL_ROUTING_SPEC.md
MIGRATION_TYPE: CARRY (verbatim)
DECISION_PRESERVATION: Router pipeline, all selection modes
(AUTO / TIER / EXPLICIT_MODEL / EXPLICIT_MODELS / AGENT_NODE_MAPPING),
hard eligibility filters (unknown = ineligible), scoring formula, fallback
policies, priority order, strategy eligibility controls, router tests, and
provider-agent routing rules carried unchanged. No decision changed.
RELATED_AUTHORITY:
  API-level model policy contract:  final_docs_v3/10_API_CONTRACTS.md §13
  Provider-agent orchestration:     final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md
  Provider/account architecture:    final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md
NOTE (non-normative): the v2 cross-reference to 21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md
now resolves to final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md.
```

---

## 1. Purpose

Router decides how a request should be executed. It is not simply a model selector.

Router outputs an Execution Plan, not a final answer.

---

## 2. Router Pipeline

```text
Request Validation
↓
Task Analysis
↓
Context Resolution
↓
Role Resolution
↓
Capability Requirements
↓
Skill Requirements
↓
Tool Requirements
↓
Execution Strategy Selection
↓
Eligibility Filtering
↓
Candidate Scoring
↓
Provider/Account Selection
↓
Execution Plan
```

---

## 3. Task Analysis Output

```json
{
  "task_type": "code_review",
  "complexity": "medium",
  "modalities_required": ["text", "code"],
  "capabilities_required": ["reasoning", "coding"],
  "tools_required": ["github.read"],
  "risk_level": "medium",
  "needs_agent": true,
  "needs_evaluation": true,
  "language": "ar"
}
```

---

## 4. Model Selection Modes

### AUTO

System chooses best candidates.

### TIER

User/admin requests tier:

```text
fast
medium
max
custom
```

### EXPLICIT_MODEL

User requests a model ID. Router must first try eligible providers for that model.

Fallback allowed only if policy allows.

---

## 5. Hard Eligibility Filters

A candidate model/provider/account is eligible only if:

```text
tenant allowed
plan entitlement allows
model active
provider active
capabilities match
modalities match
credential available
account healthy or acceptable
rate limit available
data boundary safe
tool permissions satisfied
```

Unknown = ineligible.

---

## 6. Scoring Formula

Initial configurable scoring:

```json
{
  "quality": 0.35,
  "reliability": 0.20,
  "cost": 0.15,
  "latency": 0.15,
  "context_fit": 0.10,
  "policy_preference": 0.05
}
```

Weights are policy-driven and versioned.

---

## 7. Candidate Score

```json
{
  "model_id": "uuid",
  "provider_id": "uuid",
  "account_id": "uuid",
  "score": 0.87,
  "reasons": [
    "matches required coding capability",
    "medium tier allowed by plan",
    "provider healthy",
    "low recent error rate"
  ],
  "risks": []
}
```

---

## 8. Fallback Policies

```text
none
same_model_different_provider
same_tier
lower_cost_same_capability
max_escalation
admin_defined_chain
```

Explicit model default:

```text
same_model_different_provider first
same_tier only if policy allows
```

---

## 9. Router Model Bootstrap

Router may use an LLM for task analysis, but the Router Engine is not the LLM.

To avoid recursion:

```text
Bootstrap Routing Policy selects router-analysis model.
```

Bootstrap selection must be simple, deterministic/policy-driven, and safe.

---

## 10. Router Output Contract

```json
{
  "execution_id": "uuid",
  "strategy": "pipeline",
  "nodes": [
    {
      "id": "planner",
      "type": "model_call",
      "role": "planner",
      "model_policy": {"type": "tier", "tier": "medium"},
      "skills": ["planning"],
      "tools": []
    },
    {
      "id": "reviewer",
      "type": "model_call",
      "role": "reviewer",
      "model_policy": {"type": "tier", "tier": "max"},
      "skills": ["code_review"],
      "tools": ["github.read"]
    }
  ],
  "fallback_policy": "same_tier",
  "evaluation_policy": "standard_code_review",
  "cost_snapshot": {
    "estimated_units": 2
  }
}
```

---

## 11. Router Tests

Required tests:

```text
auto selection
explicit model selection
same model provider fallback
same tier fallback
provider unavailable
account cooldown
plan denies max model
tool permission denied
unknown capability denied
router model bootstrap
cost snapshot creation
```

---

## 12. Full Model Control Policy

The Router must support explicit user/developer control over model selection without sacrificing safety, entitlement checks, or provider/account health.

Supported selection modes:

```text
AUTO
TIER
EXPLICIT_MODEL
EXPLICIT_MODELS
AGENT_NODE_MAPPING
```

---

## 13. Priority Order

When choosing models, priority is:

```text
1. Security and tenant isolation
2. User/admin entitlement
3. Availability and provider/account health
4. Explicit node-level model policy
5. Explicit request-level model policy
6. Tier constraints
7. Router optimization preference
8. Cost/performance preference
```

Explicit user choice outranks Router preference, but never outranks security, entitlement, or availability constraints.

---

## 14. Explicit Model Resolution

For `EXPLICIT_MODEL`:

```text
1. Validate model exists.
2. Validate user/tenant/plan can use it.
3. Find provider bindings for this model.
4. If provider_id provided, filter to that provider.
5. Validate provider active and allowed.
6. Select eligible account/credential.
7. If no eligible route:
   - if fallback disabled → fail clearly.
   - if fallback enabled → apply fallback policy.
```

Fallback order for explicit model default:

```text
same_model_different_provider
↓
same_tier only if explicitly allowed
↓
admin-defined fallback chain if configured
```

---

## 15. Explicit Models Strategies

### 15.1 Fallback Chain

```text
model A → if fail model B → if fail model C
```

Used for reliability and cost control.

### 15.2 Parallel Compare

```text
model A ┐
model B ├→ evaluator/judge → final
model C ┘
```

Used for quality-sensitive tasks.

### 15.3 Best-of-N

Generate multiple candidates, evaluate, return best.

### 15.4 Debate

Multiple models produce competing analyses/critiques, then a judge/finalizer produces the final result.

### 15.5 Specialist Roles

Different models perform different roles:

```text
planner
executor
coder
reviewer
security_reviewer
critic
judge
finalizer
```

---

## 16. Agent Node Mapping Resolution

In Agent Mode, model selection is resolved per node:

```text
node_model_policy
↓ fallback to
default_agent_model_policy
↓ fallback to
request_model_policy
↓ fallback to
router_auto_policy
```

The Router must record the resolved policy snapshot in the Execution Plan so future policy changes do not alter an already-started execution.

---

## 17. Strategy Eligibility Controls

Admin policies may limit:

```text
maximum number of parallel models
which users/plans can use explicit models
which users/plans can use explicit model lists
which users/plans can use debate/best_of_n
which models can be used as judge
whether provider_id can be explicitly selected
maximum cost units for multi-model strategies
```

---

## 18. Additional Router Tests

```text
explicit model allowed
explicit model denied by plan
explicit model unavailable with fallback disabled
explicit model same-model different-provider fallback
explicit models fallback_chain order
explicit models parallel_compare aggregation
explicit models debate requires judge/finalizer
node-level model policy overrides request-level policy
agent default model policy fallback
parallel model limit exceeded
provider_id explicit selection denied
policy snapshot preserved after admin policy change
```

---

## 19. Routing Agent-Capable Models

Some models/providers may expose Agent-like capabilities. The Router may select them only when the task and policy justify it.

---

### 19.1 Agent Capability Types

```text
none
basic_tool_use
provider_agent
managed_assistant
code_agent
research_agent
```

---

### 19.2 Eligibility

A provider-agent model is eligible only if:

```text
provider_agent capability is declared
user/plan allows provider-agent models
provider is active
provider account/credential is healthy
tenant boundary can be enforced
provider-side tools are policy-compatible
usage/cost limits allow it
evaluation/audit can observe the run
```

---

### 19.3 Selection Policy

Router may choose a provider-agent model when:

```text
task requires multi-step reasoning
provider agent has proven better quality for that task type
cost/time budget allows it
required tools are compatible
admin policy allows provider-managed agent execution
```

Router should avoid provider-agent models when:

```text
task is simple
provider tool behavior cannot be controlled
trace/evaluation would be insufficient
security risk is high
explicit user policy forbids provider agent usage
```

---

### 19.4 Explicit Control

Users/developers may explicitly request or forbid provider-agent models:

```json
{
  "model_policy": {
    "type": "explicit_model",
    "model_id": "provider_code_agent_x",
    "require_capabilities": ["provider_agent"],
    "allow_provider_agent": true
  }
}
```

Or forbid them:

```json
{
  "model_policy": {
    "type": "auto",
    "allow_provider_agent": false
  }
}
```

---

### 19.5 Router Invariant

```text
Selecting a provider-agent model does not transfer platform authority to the provider.
```

The platform still owns:

```text
permission checks
tool approval
usage accounting
audit
evaluation
fallback
final response formation
```

---

## 20. Routing Multiple Provider Agents

The Router may build an Agent plan that uses more than one provider-native agent.

Supported strategies:

```text
provider_agent_pipeline
provider_agent_parallel_compare
provider_agent_debate
provider_agent_specialist_roles
provider_agent_fallback_chain
```

The Router must verify:

```text
provider agents are registered
user/plan/admin policy allows them
max provider-agent count is not exceeded
provider-side tools policy is satisfied
trace/evaluation requirements can be met
cost/runtime limits are respected
```

The Router must record a policy snapshot of selected provider agents in the Execution Plan.

See `21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md`.

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–20 (purpose, router pipeline, task analysis, selection modes, eligibility filters, scoring, candidate score, fallback policies, bootstrap, output contract, tests, full model control policy, priority order, explicit model/models resolution, agent node mapping, strategy eligibility, additional tests, provider-agent routing, multi provider-agent routing) | v2 06 §1–20, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header and this
traceability section were added. All 5 selection modes kept: AUTO / TIER /
EXPLICIT_MODEL / EXPLICIT_MODELS / AGENT_NODE_MAPPING. The final "See 21_..."
pointer resolves to final_docs_v3/12 per the header note; no rule changed.
