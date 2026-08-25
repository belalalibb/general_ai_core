# 03 — Domain Model

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-006
SUPERSEDES:
  final_docs_v2/03_DOMAIN_MODEL.md
MIGRATION_TYPE: CARRY
DECISION_PRESERVATION: All entities, schemas, lifecycle states, relationship
rules, and the agent-capability model (incl. the rule
Provider Agent Capability ≠ Platform Agent Runtime) carried unchanged.
No decision changed.
```

Related authorities:
- Execution Graph / Agent Mode behavior: `12_EXECUTION_GRAPH_AND_AGENT_MODE.md`
- Provider subsystem architecture: `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md`

---

## 1. Core Entities

```text
User
Tenant
Workspace(optional)
Project(optional)
Conversation
Message
Execution
ExecutionNode
Role
Skill
Tool
Provider
ProviderAccount
Credential
Model
Capability
Policy
Plan
UsageLedger
Evaluation
LearningSample
Dataset
AuditEvent
```

---

## 2. Identity / Tenancy

### User

```yaml
User:
  id: uuid
  tenant_id: uuid
  email: string
  email_verified: boolean
  preferred_language: string
  status: active|disabled|pending
  created_at: datetime
  updated_at: datetime
```

### Tenant

```yaml
Tenant:
  id: uuid
  name: string
  type: personal|organization
  status: active|suspended
  plan_id: uuid
```

### Workspace / Project

Optional future scopes.

```yaml
Workspace:
  id: uuid
  tenant_id: uuid
  name: string

Project:
  id: uuid
  tenant_id: uuid
  workspace_id: uuid|null
  name: string
  metadata: json
```

---

## 3. Conversation / Memory

```yaml
Conversation:
  id: uuid
  tenant_id: uuid
  user_id: uuid
  project_id: uuid|null
  title: string
  status: active|archived

Message:
  id: uuid
  conversation_id: uuid
  role: user|assistant|system|tool
  content: text/json
  attachments: array
  created_at: datetime
```

Memory items:

```yaml
MemoryItem:
  id: uuid
  tenant_id: uuid
  user_id: uuid|null
  scope: global|tenant|workspace|project|conversation|role
  key: string
  value: json
  source: string
  confidence: number
  evidence_count: integer
  last_seen: datetime
  expires_at: datetime|null
```

---

## 4. Models / Providers / Accounts

### Model

```yaml
Model:
  id: uuid
  model_key: string
  display_name: string
  tier: fast|medium|max|custom
  modalities: [text, image, audio, video, code]
  capabilities: [reasoning, coding, vision, image_generation]
  context_window: integer|null
  quality_score: number|null
  speed_score: number|null
  cost_score: number|null
  reliability_score: number|null
  status: active|disabled|deprecated
```

### Provider

```yaml
Provider:
  id: uuid
  provider_key: string
  display_name: string
  status: active|disabled|maintenance
  auth_types: [api_key, oauth, session_cookie, custom]
  supports_account_pool: boolean
```

### ProviderModelBinding

يربط نفس model بأكثر من provider.

```yaml
ProviderModelBinding:
  provider_id: uuid
  model_id: uuid
  provider_model_name: string
  endpoint_ref: string
  availability: available|unavailable|degraded
  limits_metadata: json
```

### Credential

```yaml
Credential:
  id: uuid
  owner_type: platform|tenant|user
  owner_id: uuid|null
  provider_id: uuid
  credential_ref: string
  status: active|revoked|expired|invalid
```

### ProviderAccount

```yaml
ProviderAccount:
  id: uuid
  provider_id: uuid
  credential_id: uuid
  owner_type: platform|tenant|user
  lifecycle_state: READY|COOLDOWN|REFRESH_REQUIRED|AUTH_EXPIRED|INVALID|PENDING|DISABLED
  health_state: healthy|degraded|failed|unknown
  cooldown_until: datetime|null
```

---

## 5. Execution

```yaml
Execution:
  id: uuid
  tenant_id: uuid
  user_id: uuid
  conversation_id: uuid|null
  request_hash: string
  idempotency_key: string|null
  status: queued|running|waiting_approval|succeeded|failed|cancelled
  strategy: single|parallel|pipeline|debate|review_judge|map_reduce|agent|hybrid
  cost_snapshot: json
  created_at: datetime
  completed_at: datetime|null
```

```yaml
ExecutionNode:
  id: uuid
  execution_id: uuid
  node_key: string
  type: model_call|tool_call|planner|reviewer|tester|validator|aggregator
  status: pending|running|succeeded|failed|skipped|cancelled
  input_ref: string/json
  output_ref: string/json|null
  retry_count: integer
  error: json|null
```

---

## 6. Roles / Skills / Tools

```yaml
Role:
  id: uuid
  scope: system|tenant|user|project
  name: string
  version: string
  objective: text
  behavior_policies: json
  output_contract: json
  status: draft|active|disabled
```

```yaml
Skill:
  id: uuid
  name: string
  version: string
  type: instruction|workflow|tool_enabled
  source: local|imported
  provenance: json
  manifest: json
  status: imported|scanned|validated|reviewed|approved|active|disabled
```

```yaml
Tool:
  id: uuid
  name: string
  version: string
  location: server|client|hybrid
  permissions: array
  input_schema: json
  output_schema: json
  sandbox_policy: json
  approval_policy: json
  status: active|disabled
```

---

## 7. Usage / Evaluation / Learning

```yaml
UsageLedger:
  id: uuid
  tenant_id: uuid
  execution_id: uuid
  units_reserved: number
  units_settled: number
  modality_costs: json
  status: reserved|settled|refunded|failed
```

```yaml
Evaluation:
  id: uuid
  execution_id: uuid
  level: RAW|EVALUATED|VALIDATED|VERIFIED|GOLD
  score: number|null
  confidence: number|null
  evidence_ref: string|null
  graders: json
```

```yaml
LearningSample:
  id: uuid
  source_execution_id: uuid
  tenant_id: uuid|null
  eligibility: eligible|ineligible|pending
  sanitization_state: pending|passed|failed
  verification_level: RAW|EVALUATED|VALIDATED|VERIFIED|GOLD
  dataset_id: uuid|null
```

---

## 8. Relationship Rules

```text
User belongs to Tenant.
Execution belongs to Tenant and optionally Conversation/Project.
Model can be served by many Providers.
Provider can expose many Models.
Credential belongs to platform/tenant/user.
ProviderAccount wraps Credential for provider runtime.
Role can request capabilities but cannot grant permissions.
Skill can require Tools but cannot bypass Tool permissions.
Tool calls require Capability Firewall approval.
Evaluation belongs to Execution/Node.
LearningSample can only enter Dataset after eligibility + verification.
```

---

## 9. Agent-Capable Models / Provider Agent Modules

Some providers may expose a model or endpoint that behaves like an Agent, not just a normal text generation model.

Examples:

```text
provider_agent_model
provider_assistant_api
provider_code_agent
provider_research_agent
provider_tool_using_model
```

This must be modeled as a capability of a provider/model binding, not as a replacement for the platform Agent Runtime.

---

### 9.1 Model Capability Extension

A model may declare:

```yaml
Model:
  capabilities:
    - reasoning
    - coding
    - tool_use
    - provider_agent
```

Optional agent-specific metadata:

```yaml
agent_capability:
  type: none|tool_using_model|provider_agent|managed_assistant|code_agent|research_agent
  supports_threads: true
  supports_tools: true
  supports_files: true
  supports_stateful_runs: true
  supports_streaming: true
  provider_managed_state: true
```

---

### 9.2 ProviderModelBinding Extension

Because Agent behavior may differ per provider even for similar model names, agent capability is also stored at the provider binding level.

```yaml
ProviderModelBinding:
  provider_id: uuid
  model_id: uuid
  provider_model_name: string
  capabilities:
    provider_agent: true
  agent_runtime:
    provider_managed: true
    state_model: stateless|thread|run|session
    tool_policy: platform_controlled|provider_controlled|hybrid
    file_support: true
    max_steps: integer|null
```

---

### 9.3 Important Rule

```text
Provider Agent Capability ≠ Platform Agent Runtime
```

The platform may use a provider's agent-capable model as one node or strategy inside its own Execution Graph, but the platform still owns:

```text
authorization
capability firewall
tool approval
tenant isolation
usage accounting
evaluation
audit
final response policy
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–8 (entities, identity/tenancy, conversation/memory, models/providers/accounts, execution, roles/skills/tools, usage/evaluation/learning, relationship rules) | v2 03 §1–8, carried verbatim |
| 9–9.3 (agent-capable models, capability extensions, important rule + platform ownership list) | v2 03 §9–9.3, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header, related-
authority pointers, and this traceability section were added. The behavioral
specification for provider-agent orchestration lives in
`12_EXECUTION_GRAPH_AND_AGENT_MODE.md`; this document keeps the data-model view.
