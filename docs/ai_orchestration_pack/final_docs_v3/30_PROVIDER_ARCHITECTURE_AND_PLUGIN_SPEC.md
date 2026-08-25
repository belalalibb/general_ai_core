# 30 — Provider Architecture and Plugin Specification
## Capability-Driven Providers, Plugin Contracts, Optional Account Pools, and Safe Scaffolding

```text
V3 STATUS: AUTHORITATIVE
SOURCES: final_docs_v2/24_FINAL_PROVIDER_ARCHITECTURE_SPEC.md (base)
         final_docs_v2/05_PROVIDER_PLUGIN_SPEC.md (detail)
MERGED_BY_TASK: T-DOC-003
```

---

## Purpose

This is the single authoritative specification for the Provider subsystem:
provider philosophy, plugin contracts, manifests, interfaces, account pools,
health, error normalization, provider-native agents, tests, and activation.

## Audience

- Implementation Agents building the provider framework or onboarding providers.
- Reviewers verifying provider isolation and contract compliance.

## Authoritative Content

- Provider subsystem rules and boundaries (this file wins over any other doc).
- Plugin contract: manifest schema, required/optional interfaces.
- Account pool, lease, health, rate-limit, and error-normalization contracts.
- Provider-native agent rules.
- Scaffold-only state rules. Onboarding steps by provider type live in
  `31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md` (authoritative since T-DOC-004;
  successor of `final_docs_v2/23_AI_PROVIDERS_SCAFFOLDING_POLICY.md` + `25_REAL_PROVIDER_ONBOARDING_GUIDE.md`).

---

## 1. Final Provider Philosophy

A Provider is not a small `send_request()` adapter.

```text
Providers are internally independent.
Providers are externally normalized through contracts.
Providers are capability-driven.
Providers do not all share one lifecycle.
The Core never depends on provider-specific behavior.
```

A Provider is a provider-specific module that may contain its own:

```text
request runtime
auth logic
account lifecycle
session handling
discovery
model binding
operations
assets
limits
errors
health
provider-native agents
```

But the Core sees only:

```text
Provider Contract
Capabilities
Health
Normalized operations
Normalized errors
Normalized results
```

---

## 2. Non-Negotiable Boundaries

```text
Core must not import provider internals.
Core must not know provider HTTP flow.
Core must not know provider cookies/session mechanics.
Core must not store provider secrets directly.
Core must not assume all providers support generation.
Core must not assume all providers have accounts.
Core must not assume all providers have models.
Core must not assume all providers work the same way.
```

Additionally forbidden:

```text
Router calls provider HTTP directly.
Provider writes secrets to logs.
Provider bypasses account leasing.
Provider hardcodes global policy.
Provider assumes all users can use it.
Provider changes normalized contracts without versioning.
```

---

## 3. Four Concepts Must Stay Separate

The architecture must always separate:

```text
Model
Provider
Account
Credential
```

Example:

```text
Model:      claude-opus-like-model
Providers:  provider_a, provider_b, provider_c
Account:    provider_b_account_17
Credential: credential_ref_for_account_17
```

This enables:

```text
same model across multiple providers
multiple accounts per provider
user-owned credentials separated from platform credentials
provider failover without changing model identity
account failover without changing provider identity
```

---

## 4. Providers Are Capability-Driven

A provider declares what it supports. The platform must not force every
provider to implement registration, login, session refresh, account pools,
generic generate, chat, streaming, file upload, or agent behavior.

### 4.1 Common Minimum Required For Every Provider

Every real or template provider must define:

```text
provider identity
manifest
status
capabilities declaration
supported modalities
auth/credential policy declaration
health contract
error normalization contract
contract tests for declared capabilities
```

This minimum allows the Core, Router, Admin, and Evaluation systems to
reason about the provider safely.

### 4.2 Optional Modules By Capability

| Module | Required Only When |
|---|---|
| account_registration | Provider supports/needs account creation |
| login/authenticate | Provider requires login/session auth |
| session_refresh | Provider uses expiring sessions/cookies/tokens |
| account_pool | Platform manages multiple accounts for provider |
| api_key_validation | Provider uses API keys |
| oauth_flow | Provider uses OAuth |
| text_generation | Provider supports text/chat generation |
| image_generation | Provider supports image generation |
| vision_input | Provider accepts image/file input |
| audio_stt | Provider supports speech-to-text |
| audio_tts | Provider supports text-to-speech |
| embeddings | Provider supports embeddings |
| rerank | Provider supports reranking |
| moderation | Provider supports safety/moderation |
| file_upload | Provider accepts assets/files |
| streaming | Provider supports streaming output |
| async_jobs | Provider uses job/poll/result flow |
| provider_agent | Provider exposes native agent/assistant/code-agent behavior |

### 4.3 Forbidden Assumptions

The Agent implementing providers must not assume:

```text
every provider needs registration
every provider needs session refresh
every provider needs account pool
every provider can chat
every provider can generate text
every provider supports streaming
every provider has models
every provider is stateless
every provider can be called the same way
```

Provider behavior must be discovered, declared, tested, and isolated.

---

## 5. Generation Is Not One Universal Method

Do not force all providers into one `generate()` implementation.
Provider operations are capability-specific:

```text
generate_text
generate_image
transcribe_audio
synthesize_speech
create_embeddings
rerank_documents
moderate_content
analyze_vision
run_provider_agent
upload_asset
download_asset
```

A provider implements only the operations it declares.
If an operation is not declared:

```text
Provider is ineligible for that task.
```

---

## 6. Provider Package Structure

### 6.1 Minimal Plugin Layout

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

### 6.2 Mature Provider Layout (Optional Growth Path)

```text
providers/<provider_key>/
├── manifest.yaml
├── provider.*
├── config.*
├── client.*
│
├── runtime/
│   ├── request.*
│   ├── session.*
│   ├── auth.*
│   ├── parser.*
│   └── errors.*
│
├── account/
│   ├── manager.*
│   ├── create.*
│   ├── refresh.*
│   ├── validate.*
│   ├── update.*
│   └── delete.*
│
├── discovery/
│   ├── models.*
│   ├── capabilities.*
│   └── limits.*
│
├── operations/
│   ├── text_generation.*
│   ├── image_generation.*
│   ├── vision_analysis.*
│   ├── audio_stt.*
│   ├── audio_tts.*
│   ├── embeddings.*
│   ├── rerank.*
│   ├── moderation.*
│   └── provider_agent.*
│
├── assets/
│   ├── upload.*
│   └── download.*
│
├── pool/
│   ├── manager.*
│   ├── selector.*
│   ├── lease.*
│   ├── lifecycle.*
│   ├── usage.*
│   ├── cooldown.*
│   └── health.*
│
├── provider_health/
│   ├── monitor.*
│   └── circuit_breaker.*
│
└── errors.*
```

This is not mandatory for every provider from day one. Small providers may
implement fewer files as long as they satisfy the common contract and
declared capabilities.

---

## 7. Provider Manifest

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

## 8. Provider Interfaces

### 8.1 Required Provider Interface

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

Note: `generate` here is the normalized entry point; internally it dispatches
to the capability-specific operations of Section 5. A provider without a
generation capability rejects generation with `unsupported_capability`.

### 8.2 Optional Interfaces

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
```

Provider agent interfaces are defined in Section 15.

---

## 9. Provider Runtime

Provider Runtime hides provider-specific request mechanics. It may handle:

```text
HTTP verbs
headers
cookies
sessions
CSRF
token injection
custom signatures
timeouts
retry
pagination
polling
async job status
downloads
response parsing
provider-specific error parsing
```

The Core must not see these details.

---

## 10. Accounts, Pools, and Credentials

### 10.1 Account Pool Is Optional

Provider without Account Pool (e.g. simple API-key provider, embeddings
provider, moderation provider, internal/local provider) may only need:

```text
credential validation
health check
operation implementation
```

Provider with Account Pool (e.g. session-based provider, website provider,
provider with per-account rate limits or multiple platform-managed accounts)
may need:

```text
account lifecycle
usage tracking
cooldown
lease
selection
refresh
health
```

### 10.2 Account Lifecycle States

When account lifecycle exists, use normalized states:

```text
PENDING
READY
IN_USE
COOLDOWN
REFRESH_REQUIRED
AUTH_EXPIRED
RATE_LIMITED
VERIFICATION_REQUIRED
INVALID
DISABLED
```

These states describe account usability, not provider availability.

### 10.3 Account Selection Rules

Core asks Account Pool Manager for an eligible account.

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

### 10.4 Account Lease For Concurrency

If a provider uses account pools, concurrent execution must use leases:

```text
eligible accounts
↓
select account
↓
acquire lease
↓
execute provider operation
↓
update usage/state
↓
release lease
```

This prevents many requests from using the same account unsafely.

### 10.5 Credential Ownership

```text
platform_owned
user_owned
tenant_owned
```

Never mix platform and user credentials in one account pool.

Policy values:

```text
platform_only
user_only
prefer_user
auto
```

---

## 11. Health

Provider health is separate from account health.

Provider-wide states:

```text
HEALTHY
DEGRADED
UNAVAILABLE
SUSPENDED
```

Account-level states:

```text
READY
COOLDOWN
AUTH_EXPIRED
INVALID
```

Do not confuse `one account failed` with `the whole provider is down`.

---

## 12. Rate Limits Are Provider-Specific

Do not use one global rate-limit model. A provider may limit by:

```text
request count
tokens
images
audio minutes
concurrency
endpoint
account
model
time window
daily quota
provider response headers
```

The provider translates its real limits into normalized state:

```text
available
limited
cooldown_until
unknown
```

---

## 13. Provider Selection and Failure Handling

### 13.1 Provider Selection Flow

When a model can be served by multiple providers:

```text
Core request
↓
Model Registry
↓
Provider bindings for model
↓
Provider Health Filter
↓
Policy selection: random / weighted / least-used / priority
↓
Provider selected
↓
Account Pool if needed
↓
Provider Runtime
↓
Normalized result
```

For explicit model requests, provider selection should prefer healthy
eligible providers for the same model before falling back to other models.

### 13.2 Failure Handling

Account failure:

```text
account rate limited → mark COOLDOWN → try another account
account auth expired → REFRESH_REQUIRED / AUTH_EXPIRED
account invalid → INVALID / DISABLED
```

Provider failure:

```text
provider errors/timeouts increase
provider health degrades
circuit breaker opens
router skips provider temporarily
```

All providers for an explicit model fail — fallback depends on policy:

```text
same_model_different_provider
same_tier_auto
fail_if_fallback_disabled
admin-defined chain
```

---

## 14. Error Normalization

Provider-specific errors must be normalized into common categories:

```text
auth_expired
invalid_credential
rate_limited
quota_exceeded
model_unavailable
provider_unavailable
unsupported_capability
bad_request
content_rejected
timeout
retryable_server_error
non_retryable_error
```

Each normalized error must include:

```json
{
  "category": "rate_limited",
  "retryable": true,
  "retry_after_ms": 30000,
  "provider_code": "raw-code",
  "safe_message": "Provider rate limit reached."
}
```

The Core makes decisions from normalized errors only.

---

## 15. Provider-Native Agents

Some providers expose agent-like capabilities:

```text
assistant API
code agent
research agent
tool-using model
managed thread/run
```

Represent this as the `provider_agent` capability.

Binding rule:

```text
Provider Agent Capability != Platform Agent Runtime
```

The platform may use provider agents as sub-agents/nodes, while the platform
still owns:

```text
authorization
capability firewall
tool approval
tenant isolation
usage accounting
evaluation
audit
final response
```

### 15.1 Manifest Extension

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

### 15.2 Provider Agent Interface

```typescript
interface ProviderAgentModule {
  runAgent?(request: ProviderAgentRequest): Promise<ProviderAgentResponse>;
  createAgentRun?(request: ProviderAgentRunRequest): Promise<ProviderAgentRun>;
  getAgentRun?(runId: string): Promise<ProviderAgentRunStatus>;
  cancelAgentRun?(runId: string): Promise<void>;
  streamAgentRun?(runId: string): AsyncIterable<ProviderAgentEvent>;
}
```

### 15.3 Event Normalization

Provider-specific agent behavior must be normalized into platform events:

```text
provider_agent.started
provider_agent.step_started
provider_agent.tool_requested
provider_agent.tool_completed
provider_agent.message_delta
provider_agent.completed
provider_agent.failed
```

The platform must not expose raw provider agent semantics directly to the
rest of the Core.

### 15.4 Security Rule

Even if the provider agent can use tools internally, it must not bypass
platform security. Required controls:

```text
provider agent tools must be declared
provider-side tool use must be policy-controlled
platform tools still require Capability Firewall
write actions require approval where configured
provider-managed state must be tenant-scoped
provider agent traces must be auditable
```

### 15.5 Usage Rule

A provider agent may be used as:

```text
1. a normal model candidate with provider_agent capability
2. a node inside a platform Execution Graph
3. a specialist role inside Agent Mode
4. a fallback candidate for complex tasks if policy allows
```

But it must not replace the platform's routing, authorization, evaluation,
or audit layers.

### 15.6 Multiple Provider Agents as Platform Sub-Agents

A provider may expose more than one agent-like capability:

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

The platform Agent may orchestrate several provider agents from one or many
providers inside one Execution Graph. Provider modules must expose enough
metadata for routing, safety, evaluation, and usage accounting.

---

## 16. Provider Shape Examples

API-key text provider:

```text
needs api_key_validation
needs text_generation
may not need account_registration / session_refresh / account_pool
```

Session-based website provider:

```text
may need login/session_refresh
may need account_pool
may need cooldown/rate-limit management
may support text_generation or multimodal generation
```

Embeddings-only provider:

```text
needs embeddings
does not need chat/text generation or agent module
```

Image-only provider:

```text
needs image_generation
may need asset handling
does not need text chat generation
```

Provider-native agent provider:

```text
needs provider_agent capability
may need provider-managed thread/run state
may need files/tools policy
must still pass platform Capability Firewall and evaluation
```

---

## 17. Current State: No Real Providers Exist Yet

```text
No real providers are implemented yet.
Templates and examples are non-functional until replaced by real
implementations and contract tests.
```

If no real `ai_providers` exist:

```text
build scaffold only
create contracts
create manifest schema
create registry structure
create disabled diverse templates
create pending providers file
do not fake provider functionality
```

The Agent must not invent working providers, fake model names, fake
credentials, or provider-specific Core shortcuts.

### 17.1 Template Diversity — Scaffold Must Not Force One Shape

Template diversity must include the categories:

```text
chat/text, reasoning, coding, vision, image generation,
audio STT, audio TTS, embeddings, rerank, moderation/safety,
multimodal, provider-native agent
```

and demonstrate diverse shapes:

```text
API-key provider
OAuth provider
session/cookie provider
no-auth local/internal provider
text-only / image-only / embeddings-only / moderation-only provider
multimodal provider
provider-native agent provider
```

All templates must be disabled:

```text
status: template_disabled
is_template: true
is_functional: false
```

Unsupported modules must be marked
`not_supported` / `not_applicable` / `not_implemented_for_template`,
not as mandatory TODOs.

Scaffolding policy and real onboarding steps by provider type:
`31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md` (authoritative since T-DOC-004;
successor of `final_docs_v2/23_AI_PROVIDERS_SCAFFOLDING_POLICY.md` and
`final_docs_v2/25_REAL_PROVIDER_ONBOARDING_GUIDE.md`).

---

## 18. Tests Required

### 18.1 Common Provider Tests

```text
manifest schema validation
capabilities declaration validation
unsupported operations rejected
error normalization
health contract
core does not import provider internals
```

### 18.2 Template-Only State Tests

```text
templates are disabled
templates excluded from routing
templates cannot execute operations
diverse categories represented
pending real providers file exists
```

### 18.3 Real Provider Contract Tests

```text
credential validation
model discovery
capability discovery
operation contract tests for declared capabilities
generation success + generation error normalization
rate limit behavior
error mapping
health checks / account health
fallback behavior
account pool if used
lease if used
provider-agent lifecycle if used
no secret leakage in logs
```

### 18.4 Provider Agent Tests (when provider_agent declared)

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

## 19. Activation Requirements

A provider can become active only after:

```text
real manifest completed
real adapter/runtime implemented
credentials/auth handling implemented
capabilities verified
operations implemented for declared capabilities
error normalization implemented
health checks implemented
contract tests pass
security review completed
admin enablement configured
```

Do not activate incomplete providers.

---

## 20. Provider Migration Checklist

For each existing provider file being onboarded:

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

## 21. Final Provider Request Example

```text
User request
↓
Core determines required capability
↓
Model Registry finds eligible models
↓
Provider Registry finds providers for model/capability
↓
Provider health filter
↓
Provider selected
↓
Account selected only if provider needs accounts
↓
Lease acquired only if account pool is used
↓
Provider operation executed
↓
Provider-specific response parsed
↓
Normalized result returned
↓
Usage/health/account state updated
```

---

## 22. Final Rule

```text
Provider internals can be complex.
Provider contract must be stable.
Provider capabilities must be explicit.
Provider features must not be assumed.
Provider absence must not block architecture progress.
Provider functionality must never be faked.
```

---

## Resume Rule Pointer

```text
Git committed state is the only trusted progress.
Authorized task: docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md
Full protocol: final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md
```
