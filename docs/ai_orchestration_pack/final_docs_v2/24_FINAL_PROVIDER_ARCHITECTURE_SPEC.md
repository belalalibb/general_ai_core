# 24 — Final Provider Architecture Specification
## Capability-Driven Providers, Optional Account Pools, and Safe Scaffolding

---

## 1. Purpose

This document is the final focused specification for the Provider subsystem.

It consolidates the decisions from the original conversation and later refinements into one clear rule set:

```text
Providers are internally independent.
Providers are externally normalized through contracts.
Providers are capability-driven.
Providers do not all share one lifecycle.
The Core never depends on provider-specific behavior.
```

---

## 2. Final Provider Philosophy

A Provider is not a small `send_request()` adapter.

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

## 3. Non-Negotiable Boundaries

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

---

## 4. Four Concepts Must Stay Separate

The architecture must always separate:

```text
Model
Provider
Account
Credential
```

Example:

```text
Model:
  claude-opus-like-model

Providers:
  provider_a
  provider_b
  provider_c

Accounts:
  provider_b_account_17

Credential:
  credential_ref_for_account_17
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

## 5. Provider Is Capability-Driven

A provider declares what it supports.

The platform must not force every provider to implement:

```text
registration
login
session refresh
account pool
generic generate
chat
streaming
file upload
agent behavior
```

Instead, each provider declares capabilities and operations.

---

## 6. Common Minimum Required For Every Provider

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

This minimum allows the Core, Router, Admin, and Evaluation systems to reason about the provider safely.

---

## 7. Optional Modules By Capability

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

---

## 8. Generation Is Not One Universal Method

Do not force all providers into one `generate()` implementation.

Provider operations should be capability-specific:

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

## 9. Provider Internal Structure

A mature provider may look like:

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

But this is not mandatory for every provider from day one.

Small providers may implement fewer files as long as they satisfy the common contract and declared capabilities.

---

## 10. Provider Runtime

Provider Runtime hides provider-specific request mechanics.

It may handle:

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

## 11. Account Pool Is Optional

A provider uses Account Pool only if needed.

### Provider without Account Pool

Example:

```text
simple API-key provider
embeddings provider
moderation provider
internal/local provider
```

May only need:

```text
credential validation
health check
operation implementation
```

### Provider with Account Pool

Example:

```text
session-based provider
website provider
provider with per-account rate limits
provider with multiple platform-managed accounts
```

May need:

```text
account lifecycle
usage tracking
cooldown
lease
selection
refresh
health
```

---

## 12. Account Lifecycle States

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

---

## 13. Provider Health Is Separate From Account Health

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

Do not confuse:

```text
one account failed
```

with:

```text
the whole provider is down
```

---

## 14. Rate Limits Are Provider-Specific

Do not use one global rate-limit model.

A provider may limit by:

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

## 15. Account Lease For Concurrency

If a provider uses account pools, concurrent execution must use leases.

Flow:

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

---

## 16. Provider Selection Flow

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

For explicit model requests, provider selection should prefer healthy eligible providers for the same model before falling back to other models.

---

## 17. Failure Handling

### Account failure

```text
account rate limited → mark COOLDOWN → try another account
account auth expired → REFRESH_REQUIRED / AUTH_EXPIRED
account invalid → INVALID / DISABLED
```

### Provider failure

```text
provider errors/timeouts increase
provider health degrades
circuit breaker opens
router skips provider temporarily
```

### All providers for explicit model fail

Fallback depends on policy:

```text
same_model_different_provider
same_tier_auto
fail_if_fallback_disabled
admin-defined chain
```

---

## 18. Error Normalization

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

The Core makes decisions from normalized errors only.

---

## 19. Provider-Native Agents

Some providers may expose agent-like capabilities:

```text
assistant API
code agent
research agent
tool-using model
managed thread/run
```

Represent this as:

```text
provider_agent capability
```

Do not treat it as the platform Agent Runtime.

Rule:

```text
Provider Agent Capability != Platform Agent Runtime
```

The platform may use provider agents as sub-agents/nodes, while the platform still owns:

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

---

## 20. If No Real Providers Exist Yet

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

Template diversity must include:

```text
chat/text
reasoning
coding
vision
image generation
audio STT
audio TTS
embeddings
rerank
moderation/safety
multimodal
provider-native agent
```

All templates must be disabled:

```text
status: template_disabled
is_template: true
is_functional: false
```

---

## 21. Scaffold Must Not Force One Shape

Provider templates should demonstrate diversity:

```text
API-key provider
OAuth provider
session/cookie provider
no-auth local/internal provider
text-only provider
image-only provider
embeddings-only provider
moderation-only provider
multimodal provider
provider-native agent provider
```

Unsupported modules must be marked:

```text
not_supported
not_applicable
not_implemented_for_template
```

not as mandatory TODOs.

---

## 22. Tests Required

### Common provider tests

```text
manifest schema validation
capabilities declaration validation
unsupported operations rejected
error normalization
health contract
core does not import provider internals
```

### Template-only state tests

```text
templates are disabled
templates excluded from routing
templates cannot execute operations
diverse categories represented
pending real providers file exists
```

### Real provider tests

```text
credential validation
operation contract tests for declared capabilities
rate limit behavior
error mapping
health checks
account pool if used
lease if used
provider-agent lifecycle if used
no secret leakage
```

---

## 23. Activation Requirements

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

## 24. Final Provider Request Example

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

## 25. Final Rule

```text
Provider internals can be complex.
Provider contract must be stable.
Provider capabilities must be explicit.
Provider features must not be assumed.
Provider absence must not block architecture progress.
Provider functionality must never be faked.
```
