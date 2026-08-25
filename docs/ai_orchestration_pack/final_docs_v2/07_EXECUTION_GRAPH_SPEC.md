# 07 — Execution Graph Specification

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-005)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

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
```

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

## 12. Execution Tests

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

## 17. Additional Execution Tests

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

## 18. Provider-Agent Nodes

An Execution Graph node may use a provider-agent model or provider-managed assistant as its execution backend.

This is represented as a node type or model capability, not as a replacement for the platform graph.

---

### 18.1 Provider-Agent Node Example

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

---

### 18.2 Provider-Agent Node Lifecycle

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

---

### 18.3 When to Use Provider-Agent Nodes

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

---

### 18.4 Control Rule

A provider-agent node cannot create platform-side effects directly.

Any external effect must still go through:

```text
Capability Firewall
Approval Gate
Audit
Usage Accounting
```

---

## 19. Multi Provider-Agent Orchestration

The platform Agent Runtime may orchestrate multiple provider-native agents within one Execution Graph.

Example:

```text
Platform Planner
↓
Provider Research Agent
↓
Provider Code Agent
↓
Provider Review Agent
↓
Platform Judge
↓
Platform Finalizer
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

See `21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md`.
