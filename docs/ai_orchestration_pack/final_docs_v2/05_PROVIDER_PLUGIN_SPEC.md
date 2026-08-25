# 05 — Provider Plugin Specification

---

## 1. Purpose

Provider modules isolate all provider-specific behavior from the Core.

The Core must never contain provider-specific HTTP, cookies, rate-limit quirks, or model naming assumptions.

---

## 2. Provider Package Layout

```text
providers/<provider_key>/
  manifest.yaml
  adapter.ts|py
  auth.ts|py
  accounts.ts|py
  models.ts|py
  generate.ts|py
  assets.ts|py
  health.ts|py
  errors.ts|py
  tests/
```

Exact language/layout may vary, but boundaries must remain.

---

## 3. Provider Manifest

```yaml
id: provider_x
name: Provider X
version: 1.0.0
status: active

auth:
  types:
    - api_key
    - session_cookie
  supports_refresh: true

account_pool:
  supported: true
  lease_required: true
  fencing_required: true

capabilities:
  chat: true
  reasoning: true
  code: true
  vision_input: true
  image_generation: false
  audio_input: false
  audio_output: false
  file_upload: true
  browser: false
  agent_module: false

models:
  discovery: dynamic
  static_models: []

rate_limits:
  strategy: provider_defined
  dimensions:
    - account
    - model
    - endpoint
    - time_window

health:
  checks:
    - auth_valid
    - endpoint_available
    - quota_available

errors:
  mapping: provider_x_error_map
```

---

## 4. Required Provider Interface

```typescript
interface ProviderAdapter {
  getManifest(): ProviderManifest;
  validateCredential(credentialRef: string): Promise<CredentialHealth>;
  discoverModels(account?: ProviderAccount): Promise<ModelBinding[]>;
  getCapabilities(): Promise<ProviderCapabilities>;
  generate(request: ProviderGenerateRequest): Promise<ProviderGenerateResponse>;
  healthCheck(scope: HealthScope): Promise<ProviderHealth>;
  normalizeError(error: unknown): ProviderError;
}
```

---

## 5. Optional Interfaces

```typescript
interface ProviderAccountLifecycle {
  createAccount?(): Promise<ProviderAccount>;
  refreshAccount?(account: ProviderAccount): Promise<AccountRefreshResult>;
  disableAccount?(accountId: string): Promise<void>;
}

interface ProviderAssets {
  uploadFile?(file: FileRef): Promise<AssetRef>;
  downloadFile?(asset: AssetRef): Promise<FileRef>;
}

interface ProviderAgentModule {
  runAgent?(request: ProviderAgentRequest): Promise<ProviderAgentResponse>;
}
```

Provider agent module is a capability, not the platform architecture.

---

## 6. Account Selection Rules

Core asks Account Pool Manager for eligible account.

Eligibility filters:

```text
provider active
credential active
account lifecycle READY
not in cooldown
tenant/user policy allows it
rate limit budget available
model binding available
```

Selection may consider:

```text
least recently used
available quota
health
latency
error rate
priority
owner policy
```

---

## 7. Credential Ownership

```text
platform_owned
user_owned
tenant_owned
```

Never mix platform and user credentials in one account pool.

Policy:

```text
platform_only
user_only
prefer_user
auto
```

---

## 8. Provider Error Normalization

Provider-specific errors must map to normalized categories:

```text
auth_expired
invalid_credential
rate_limited
quota_exceeded
model_unavailable
provider_unavailable
bad_request
content_rejected
timeout
retryable_server_error
non_retryable_error
```

Each error must include:

```json
{
  "category": "rate_limited",
  "retryable": true,
  "retry_after_ms": 30000,
  "provider_code": "raw-code",
  "safe_message": "Provider rate limit reached."
}
```

---

## 9. Contract Tests Required Per Provider

```text
manifest validation
credential validation
model discovery
capability discovery
generation success
generation error normalization
rate limit handling
account health
fallback behavior
no secret leakage in logs
```

---

## 10. Provider Migration Checklist

For each existing provider file:

```text
1. Inventory current capabilities.
2. Identify auth method.
3. Identify models and modalities.
4. Identify request/generate flows.
5. Identify upload/download support.
6. Identify rate limit behavior.
7. Identify error patterns.
8. Write manifest.
9. Implement adapter.
10. Add contract tests.
11. Register provider.
12. Verify with isolated test.
13. Commit.
```

---

## 11. Forbidden

```text
Core imports provider internals.
Router calls provider HTTP.
Provider writes secrets to logs.
Provider bypasses account leasing.
Provider hardcodes global policy.
Provider assumes all users can use it.
Provider changes normalized contracts without versioning.
```

---

## 12. Provider Agent Capability

Some providers may expose Agent-like functionality, such as:

```text
assistant APIs
managed agent runs
code agents
research agents
tool-using models
stateful threads/runs
```

This must be represented as an optional Provider capability.

---

### 12.1 Manifest Extension

```yaml
capabilities:
  chat: true
  reasoning: true
  tool_use: true
  provider_agent: true

agent_module:
  supported: true
  type: managed_assistant
  state_model: thread_run
  supports_files: true
  supports_provider_tools: true
  supports_platform_tools: false
  supports_streaming: true
  max_steps: null
  approval_integration: required
```

---

### 12.2 Provider Agent Interface

If a provider supports agent-like execution, it may implement:

```typescript
interface ProviderAgentModule {
  createAgentRun?(request: ProviderAgentRunRequest): Promise<ProviderAgentRun>;
  getAgentRun?(runId: string): Promise<ProviderAgentRunStatus>;
  cancelAgentRun?(runId: string): Promise<void>;
  streamAgentRun?(runId: string): AsyncIterable<ProviderAgentEvent>;
}
```

---

### 12.3 Normalization Rule

Provider-specific Agent behavior must be normalized into platform events:

```text
provider_agent.started
provider_agent.step_started
provider_agent.tool_requested
provider_agent.tool_completed
provider_agent.message_delta
provider_agent.completed
provider_agent.failed
```

The platform must not expose raw provider agent semantics directly to the rest of the Core.

---

### 12.4 Security Rule

Even if the provider agent can use tools internally, the platform must not allow it to bypass platform security.

Required controls:

```text
provider agent tools must be declared
provider-side tool use must be policy-controlled
platform tools still require Capability Firewall
write actions require approval where configured
provider-managed state must be tenant-scoped
provider agent traces must be auditable
```

---

### 12.5 Usage Rule

A provider agent may be used as:

```text
1. a normal model candidate with provider_agent capability
2. a node inside a platform Execution Graph
3. a specialist role inside Agent Mode
4. a fallback candidate for complex tasks if policy allows
```

But it must not replace the platform's routing, authorization, evaluation, or audit layers.

---

### 12.6 Required Tests

```text
provider agent manifest validation
provider agent run lifecycle
provider agent error normalization
provider agent event normalization
provider agent tool request blocked without permission
provider agent tenant isolation
provider-managed state cleanup/cancellation
provider agent usage accounting
```

---

## 13. Multiple Provider Agents as Platform Sub-Agents

A provider may expose more than one agent-like capability.

Example:

```text
provider_x.code_agent
provider_x.research_agent
provider_x.image_agent
provider_x.review_agent
```

Each must be registered independently with:

```text
id
type
capabilities
modalities
state model
tool behavior
risk level
allowed roles
required controls
```

The platform Agent may orchestrate several provider agents from one or many providers inside one Execution Graph.

Provider modules must expose enough metadata for routing, safety, evaluation, and usage accounting.

---

## 14. No Real Providers Yet

If no real `ai_providers` or provider implementations exist yet, the Agent must create only the provider framework and disabled diverse templates.

It must not invent working providers, fake model names, fake credentials, or provider-specific Core shortcuts.

See:

```text
23_AI_PROVIDERS_SCAFFOLDING_POLICY.md
```
