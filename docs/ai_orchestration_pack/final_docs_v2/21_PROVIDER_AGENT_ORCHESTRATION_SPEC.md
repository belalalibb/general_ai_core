# 21 — Provider Agent Orchestration Specification
## Using Multiple Provider-Native Agents Inside the Platform Agent

---

## 1. Purpose

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

---

## 2. Core Concept

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

## 3. Critical Rule

```text
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

## 4. Terminology

| Term | Meaning |
|---|---|
| Platform Agent | The product's own Agent Runtime / Execution Graph orchestrator |
| Provider Agent | Agent-like capability exposed by an external provider |
| Sub-Agent Node | A node in the platform graph that delegates work to a provider agent |
| Specialist Agent | Provider agent selected for a specific role such as coder/researcher/reviewer |
| Agent Ensemble | Multiple provider agents executed in parallel/debate/pipeline and aggregated |

---

## 5. Provider Agent Registry

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

## 6. Provider Agent as Execution Node

A provider agent can be used as a node:

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

---

## 7. Multiple Provider Agents in One Platform Agent

The platform may use multiple provider agents in several patterns.

### 7.1 Pipeline

```text
Platform Planner
↓
Provider A Research Agent
↓
Provider B Code Agent
↓
Provider C Review Agent
↓
Platform Finalizer
```

### 7.2 Parallel Compare

```text
Provider A Agent ┐
Provider B Agent ├→ Platform Evaluator/Judge → Final
Provider C Agent ┘
```

### 7.3 Debate

```text
Provider A Agent proposes solution
Provider B Agent critiques
Provider C Agent gives alternative
Platform Judge selects/merges
```

### 7.4 Specialist Roles

```text
planner: platform model
researcher: provider research agent
coder: provider code agent
security_reviewer: platform or provider security agent
judge: platform-controlled judge model
finalizer: platform model
```

### 7.5 Fallback Chain

```text
Try Provider A Agent
if unavailable → Provider B Agent
if low quality → Provider C Agent or platform-native workflow
```

---

## 8. Agent Orchestration Policy

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

## 9. Routing Rules

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

## 10. Control and Safety

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

## 11. Traceability

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

## 12. Evaluation and Aggregation

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

## 13. Failure Handling

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

## 14. Admin Controls

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

## 15. Required Tests

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

## 16. Final Rule

The product Agent can use many provider agents, but the platform remains the commander.

```text
Provider agents execute delegated work.
Platform Agent orchestrates, controls, evaluates, and finalizes.
```
