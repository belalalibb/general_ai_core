# 12 — Execution Graph and Agent Mode
## Execution Graph Specification + Provider-Agent Orchestration (Single Authority)

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-005
SUPERSEDES:
  final_docs_v2/07_EXECUTION_GRAPH_SPEC.md
  final_docs_v2/21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md
DECISION_PRESERVATION: All decisions, contracts, schemas, invariants, and tests
from both V2 sources are preserved. Structure merged; no decision changed.
```

This document is the single authority for the Execution Graph, Agent Mode, and
the orchestration of provider-native agents inside platform executions.
Provider-agent orchestration is Execution Graph behavior, not a separate subsystem.

Related authorities:
- Provider subsystem architecture: `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md`
- Provider scaffolding / onboarding state: `31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md`

---

# PART I — EXECUTION GRAPH CORE

---

## 1. Purpose

Execution Graph turns a task into one or more controlled execution nodes.

Agent Mode is implemented as an execution graph, not a boolean.

---

## 2. Supported Strategies

```text
single
parallel
pipeline
debate
review_judge
map_reduce
agent
hybrid
```

---

## 3. Execution Graph Schema

```json
{
  "id": "execution_uuid",
  "strategy": "agent",
  "status": "running",
  "nodes": [],
  "edges": [],
  "policies": {
    "timeout_ms": 600000,
    "retry_policy": "standard",
    "approval_policy": "tool_write_requires_approval",
    "evaluation_policy": "standard"
  }
}
```

---

## 4. Node Schema

```json
{
  "id": "review_code",
  "type": "model_call",
  "role": "code_reviewer",
  "input_source": ["user_request", "github.files"],
  "model_policy": {
    "type": "tier",
    "tier": "medium"
  },
  "skills": ["code_review"],
  "tools": ["github.read"],
  "output_schema": null,
  "retry_policy": {
    "max_attempts": 2,
    "retry_on": ["timeout", "retryable_provider_error"]
  },
  "timeout_ms": 120000,
  "evaluation_policy": "code_review_basic"
}
```

---

## 5. Node Types

```text
planner
model_call
tool_call
aggregator
reviewer
tester
validator
approval_gate
human_input
finalizer
provider_agent_call
```

`provider_agent_call` is defined in Part II. It is a node type inside this graph,
never a replacement for the platform graph.

---

## 6. Node Lifecycle

```text
pending
ready
running
waiting_approval
succeeded
failed
skipped
cancelled
```

---

## 7. Edge Schema

```json
{
  "from": "planner",
  "to": "executor",
  "condition": "success"
}
```

Conditions:

```text
success
failure
always
score_below_threshold
approval_granted
approval_denied
```

---

## 8. Agent Workflow Examples

### IDE Workflow

```text
Understand
→ Plan
→ Modify/Generate Patch
→ Run Tests
→ Review Diff
→ Security Check
→ Human Approval
→ Commit/PR
```

### Marketing Workflow

```text
Understand Product
→ Research
→ Generate Variants
→ Evaluate
→ Optimize
→ Final Output
```

---

## 9. Durable Workflow Runtime

The system should rely on a durable workflow runtime for:

```text
state persistence
node progression
timeouts
retries
crash recovery
long-running jobs
```

Do not build an ad-hoc workflow engine inside Core.

---

## 10. Idempotency

Each node must be idempotent when it can be retried.

Tool write operations require stronger idempotency keys, e.g.:

```text
tenant_id + execution_id + node_id + operation_hash
```

---

## 11. Approval Gates

Tool actions requiring approval:

```text
write file
create commit
create PR
merge PR
send external message
spend high cost
use user credential for sensitive action
```

Approval result must be auditable.

---

## 12. Execution Tests (Core)

```text
single success
pipeline success
node retry
node timeout
tool approval required
worker crash recovery
duplicate delivery
stale worker fencing
execution cancellation
partial failure with fallback
finalizer aggregation
```

---

## 13. Per-Node Model Policy in Agent Mode

Each execution node may have its own model policy.

This allows full control over which models are used for planning, execution, reviewing, judging, or finalization.

Example:

```json
{
  "nodes": [
    {
      "id": "planner",
      "type": "model_call",
      "role": "planner",
      "model_policy": {
        "type": "tier",
        "tier": "medium"
      }
    },
    {
      "id": "coder",
      "type": "model_call",
      "role": "coder",
      "model_policy": {
        "type": "explicit_model",
        "model_id": "coding_model_strong",
        "allow_fallback": true,
        "fallback_scope": "same_model_different_provider"
      }
    },
    {
      "id": "reviewer",
      "type": "model_call",
      "role": "reviewer",
      "model_policy": {
        "type": "explicit_models",
        "models": [
          {"model_id": "reviewer_a"},
          {"model_id": "reviewer_b"}
        ],
        "selection_strategy": "parallel_compare"
      }
    },
    {
      "id": "finalizer",
      "type": "aggregator",
      "role": "finalizer",
      "model_policy": {
        "type": "tier",
        "tier": "max"
      }
    }
  ]
}
```

---

## 14. Multi-Model Node Behavior

A node with `explicit_models` may internally expand into subnodes:

```text
reviewer:model_a ┐
reviewer:model_b ├→ reviewer_aggregator → next node
reviewer:model_c ┘
```

The execution runtime must record each subnode separately for traceability, cost accounting, evaluation, and debugging.

---

## 15. Judge / Aggregator Requirements

Strategies such as:

```text
parallel_compare
best_of_n
debate
```

must define either:

```text
1. a deterministic aggregation rule, or
2. a judge model policy, or
3. a downstream finalizer node.
```

If no judge/aggregation rule exists, the request is invalid.

---

## 16. Cost and Limit Controls

Multi-model agent nodes must respect:

```text
max parallel models
max cost units
max runtime
plan entitlement
admin policy
user budget
```

If the requested mapping exceeds limits, the system must either:

```text
return a validation error
or request user confirmation/upgrade
```

based on policy.

---

## 17. Additional Execution Tests (Per-Node Model Policy)

```text
node-specific explicit model used
node-specific explicit model denied
multi-model node expands to subnodes
parallel reviewer aggregation
missing judge rejected
node policy snapshot stored
cost limit blocks multi-model execution
fallback within node model policy
```

---

# PART II — PROVIDER-AGENT ORCHESTRATION
## Using Multiple Provider-Native Agents Inside the Platform Agent

---

## 18. Purpose

The platform's Agent Mode must be able to orchestrate multiple provider-native agents as sub-agents inside one controlled platform execution.

This means the product's own Agent Runtime can use agents exposed by providers, such as:

```text
Provider A Code Agent
Provider B Research Agent
Provider C Image Agent
Provider D Assistant Agent
Provider E Tool-Using Agent
```

as controlled execution nodes or specialist agents.

An Execution Graph node may use a provider-agent model or provider-managed assistant as its execution backend.
This is represented as a node type or model capability, not as a replacement for the platform graph.

---

## 19. Core Concept

```text
Platform Agent Runtime
    ↓ orchestrates
Execution Graph
    ↓ contains nodes
Provider Agent Nodes
    ↓ call
Provider-Native Agents
```

The platform Agent is the orchestrator. Provider agents are resources/sub-agents.

---

## 20. Critical Rule — BINDING

```text
Provider Agent Capability != Platform Agent Runtime.
Provider Agents are subordinate execution resources.
They do not become the platform authority.
```

Even when using provider-native agents, the platform still owns:

```text
routing
authorization
capability firewall
tenant isolation
tool approval
usage accounting
audit
evaluation
aggregation
final response
fallback/recovery
```

---

## 21. Terminology

| Term | Meaning |
|---|---|
| Platform Agent | The product's own Agent Runtime / Execution Graph orchestrator |
| Provider Agent | Agent-like capability exposed by an external provider |
| Sub-Agent Node | A node in the platform graph that delegates work to a provider agent |
| Specialist Agent | Provider agent selected for a specific role such as coder/researcher/reviewer |
| Agent Ensemble | Multiple provider agents executed in parallel/debate/pipeline and aggregated |

---

## 22. Provider Agent Registry

Provider-native agents must be registered explicitly.

```yaml
provider_agent:
  id: provider_a_code_agent
  provider_id: provider_a
  display_name: Provider A Code Agent
  type: code_agent
  status: active
  capabilities:
    - coding
    - repository_analysis
    - tool_use
  modalities:
    - text
    - code
    - files
  state_model: thread_run
  provider_managed_state: true
  supports_streaming: true
  supports_files: true
  supports_provider_tools: true
  supports_platform_tools: false
  risk_level: medium
  allowed_roles:
    - coder
    - code_reviewer
  required_controls:
    - audit
    - evaluation
    - capability_firewall
```

---

## 23. Provider-Agent Node

### 23.1 Node Example (model-policy form)

```json
{
  "id": "provider_code_agent",
  "type": "provider_agent_call",
  "role": "code_agent",
  "model_policy": {
    "type": "explicit_model",
    "model_id": "provider_code_agent_x",
    "require_capabilities": ["provider_agent"]
  },
  "input_source": ["user_request", "repo_context"],
  "tool_policy": {
    "provider_side_tools_allowed": false,
    "platform_tools_allowed": ["github.read"],
    "approval_required_for": ["github.write"]
  },
  "timeout_ms": 600000,
  "evaluation_policy": "provider_agent_code_review"
}
```

### 23.2 Node Example (explicit provider-agent form)

```json
{
  "id": "code_agent_a",
  "type": "provider_agent_call",
  "role": "coder",
  "provider_agent_policy": {
    "type": "explicit_provider_agent",
    "provider_agent_id": "provider_a_code_agent"
  },
  "input_source": ["task_plan", "repo_context"],
  "allowed_tools": ["github.read"],
  "provider_side_tools_allowed": false,
  "timeout_ms": 600000,
  "evaluation_policy": "code_agent_output_review"
}
```

### 23.3 Provider-Agent Node Lifecycle

Provider-agent node events must be normalized into the platform node lifecycle:

```text
pending
ready
running
waiting_approval
succeeded
failed
cancelled
```

Provider-specific intermediate events are stored as trace events, not leaked as Core semantics.

### 23.4 When to Use Provider-Agent Nodes

Use when:

```text
provider agent is demonstrably better for this task
the task benefits from provider-managed state or native tools
platform can still audit/evaluate/control the run
cost and policy allow it
```

Avoid when:

```text
platform needs strict step-by-step control
provider agent tool behavior is opaque
security risk is high
task is simple enough for normal model_call nodes
```

### 23.5 Control Rule

A provider-agent node cannot create platform-side effects directly.

Any external effect must still go through:

```text
Capability Firewall
Approval Gate
Audit
Usage Accounting
```

---

## 24. Orchestration Patterns — Multiple Provider Agents in One Platform Agent

The platform Agent Runtime may orchestrate multiple provider-native agents within one Execution Graph.

### 24.1 Pipeline

```text
Platform Planner
↓
Provider A Research Agent
↓
Provider B Code Agent
↓
Provider C Review Agent
↓
Platform Judge
↓
Platform Finalizer
```

### 24.2 Parallel Compare

```text
Provider A Agent ┐
Provider B Agent ├→ Platform Evaluator/Judge → Final
Provider C Agent ┘
```

### 24.3 Debate

```text
Provider A Agent proposes solution
Provider B Agent critiques
Provider C Agent gives alternative
Platform Judge selects/merges
```

### 24.4 Specialist Roles

```text
planner: platform model
researcher: provider research agent
coder: provider code agent
security_reviewer: platform or provider security agent
judge: platform-controlled judge model
finalizer: platform model
```

### 24.5 Fallback Chain

```text
Try Provider A Agent
if unavailable → Provider B Agent
if low quality → Provider C Agent or platform-native workflow
```

Provider agents can be used as:

```text
specialist nodes
parallel competitors
debate participants
fallback candidates
review/judge assistants
```

But they remain subordinate nodes. The platform graph still owns state, permissions, audit, evaluation, and final response formation.

---

## 25. Agent Orchestration Policy

Request example:

```json
{
  "mode": "agent",
  "agent_policy": {
    "workflow": "advanced_code_review",
    "provider_agents": {
      "allow_provider_agents": true,
      "selection_mode": "specialist_roles",
      "max_provider_agents": 3,
      "provider_side_tools_allowed": false,
      "require_platform_evaluation": true
    },
    "node_agent_policies": {
      "researcher": {
        "type": "explicit_provider_agent",
        "provider_agent_id": "provider_b_research_agent"
      },
      "coder": {
        "type": "explicit_provider_agent",
        "provider_agent_id": "provider_a_code_agent"
      },
      "reviewer": {
        "type": "provider_agent_pool",
        "allowed_provider_agents": [
          "provider_c_review_agent",
          "provider_d_review_agent"
        ],
        "selection_strategy": "parallel_compare"
      }
    }
  }
}
```

---

## 26. Routing Rules for Provider Agents

The Router may select provider agents when:

```text
task requires multi-step specialist work
provider agent is registered and active
user/plan/admin policy allows provider agents
required capabilities match
provider/account health is acceptable
audit/evaluation visibility is sufficient
cost and runtime budgets allow it
```

The Router must avoid provider agents when:

```text
task is simple
provider behavior is opaque for the required action
provider-side tools cannot be controlled
security risk is too high
user explicitly forbids provider agents
admin policy disables them
```

---

## 27. Control and Safety

Provider agents cannot directly perform platform-side actions.

Any action that affects external systems must pass through:

```text
Capability Firewall
Approval Gate
Audit
Usage Accounting
Tenant Scope Check
```

Provider-side tools default to disabled unless explicitly allowed by admin policy.

---

## 28. Traceability

Every provider-agent run must record:

```text
provider_agent_id
provider_id
model/provider binding
account/credential reference
input summary
output reference
provider run/thread/session id if applicable
intermediate events if available
tool requests if available
cost estimate/actual
evaluation result
final contribution to platform answer
```

---

## 29. Evaluation and Aggregation

Outputs from provider agents must be evaluated before final use when:

```text
multiple agents disagree
task is security-sensitive
provider agent used provider-side tools
output affects code/files/external systems
result enters learning pipeline
```

Aggregation options:

```text
best_score_wins
judge_model
platform_finalizer
human_review
weighted_merge
```

---

## 30. Failure Handling

If a provider agent fails:

```text
retry if safe
fallback to another provider agent if policy allows
fallback to platform-native workflow if possible
return partial result if useful
record failure and provider health signal
```

Provider-agent failure must not corrupt platform execution state.

---

## 31. Admin Controls

Admin can configure:

```text
which provider agents are enabled
which plans can use provider agents
which provider agents are visible to users
max provider agents per execution
allowed orchestration strategies
whether provider-side tools are allowed
whether provider-managed state is allowed
required evaluation policy
runtime/cost limits
fallback to platform-native workflow
```

---

## 32. Required Tests (Provider-Agent Orchestration)

```text
register provider agent
explicit provider agent selection
provider agent denied by plan
multiple provider agents parallel_compare
specialist_roles mapping
provider-side tools disabled by default
provider agent output evaluated before final
provider agent fallback
provider agent trace recorded
provider agent cannot bypass capability firewall
provider-managed state tenant-scoped
```

---

## 33. Final Rule

The product Agent can use many provider agents, but the platform remains the commander.

```text
Provider agents execute delegated work.
Platform Agent orchestrates, controls, evaluates, and finalizes.
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–8 (purpose, strategies, graph/node/edge schemas, node types, lifecycle, workflows) | v2 07 §1–8 (node types list extended with `provider_agent_call`, already implied by v2 07 §18) |
| 9–12 (durable runtime, idempotency, approval gates, core tests) | v2 07 §9–12 |
| 13–17 (per-node model policy, multi-model nodes, judge/aggregator, cost limits, tests) | v2 07 §13–17 |
| 18 (purpose of provider-agent orchestration) | v2 21 §1 + v2 07 §18 |
| 19 (core concept) | v2 21 §2 |
| 20 (critical rule + platform ownership list) | v2 21 §3 + index-mandated rule "Provider Agent Capability != Platform Agent Runtime" |
| 21 (terminology) | v2 21 §4 |
| 22 (provider agent registry) | v2 21 §5 |
| 23 (provider-agent node: both example forms, lifecycle, when-to-use, control rule) | v2 07 §18.1–18.4 + v2 21 §6 |
| 24 (orchestration patterns incl. pipeline with Platform Judge, roles list) | v2 21 §7 + v2 07 §19 |
| 25 (agent orchestration policy) | v2 21 §8 |
| 26 (routing rules) | v2 21 §9 |
| 27 (control and safety) | v2 21 §10 + v2 07 §18.4 (deduplicated) |
| 28 (traceability) | v2 21 §11 |
| 29 (evaluation and aggregation) | v2 21 §12 |
| 30 (failure handling) | v2 21 §13 |
| 31 (admin controls) | v2 21 §14 |
| 32 (required tests) | v2 21 §15 |
| 33 (final rule) | v2 21 §16 |

No decision, schema, rule list, or test case was dropped. Duplicated content
(the "external effects must pass Capability Firewall / Approval Gate / Audit /
Usage Accounting" rule and the multi-agent pipeline example, stated in both
v2 07 §18–19 and v2 21) is stated once with both source variants preserved
(§23.5 keeps the node-level form; §27 keeps the superset with Tenant Scope Check).
