# 31 — Provider Scaffolding & Real Provider Onboarding
## Scaffold-Only State Policy + The Path to Real Providers, by Provider Type

```text
STATUS: AUTHORITATIVE (V3)
AUTHORED_BY_TASK: T-DOC-004
SOURCES (V2, now SUPERSEDED):
- final_docs_v2/23_AI_PROVIDERS_SCAFFOLDING_POLICY.md   (scaffold-only state policy)
- final_docs_v2/25_REAL_PROVIDER_ONBOARDING_GUIDE.md    (real provider onboarding guide)
AUTHORITY SWITCH: final_docs_v3/00_INDEX.md (MIGRATION STATUS table)
RELATED AUTHORITATIVE SPEC:
- final_docs_v3/30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md (provider architecture, contracts, capability model)
```

This document is the single authority for the provider lifecycle stage question:
**"No real providers exist yet — what now, and how do real providers get added later?"**

Part I defines the scaffold-only state policy (what must and must not exist before any real provider).
Part II defines the onboarding guide (how to add real providers later, by provider type).

---

# PART I — SCAFFOLD-ONLY STATE POLICY

---

## 1. Purpose and Current State — Important

This policy defines what the Agent must do when the project does not yet contain real AI provider implementations.

The goal is to avoid blocking the architecture while also avoiding fake, invented, or misleading provider integrations.

At the current documentation/repository state:

```text
There are NO real AI providers implemented yet.
```

Any provider-related structure described in the documentation is currently intended as:

```text
architecture
contracts
schemas
templates
examples
scaffolding
future implementation guide
```

It must not be interpreted as working provider integration.

---

## 2. Core Rule

If no real `ai_providers` exist yet:

```text
Create provider structure and contracts only.
Do not invent working providers.
Do not claim provider integration is complete.
Do not hardcode provider-specific behavior into Core.
```

Real providers will be added later.

---

## 3. Required Behavior

When the Agent inspects the repo and finds:

```text
no ai_providers directory
or
no real provider implementations
or
only incomplete/unknown provider files
```

it must:

```text
1. Create the provider framework/scaffold.
2. Create provider contracts/interfaces.
3. Create manifest schemas.
4. Create registry structure.
5. Create common error/capability types.
6. Create disabled template providers for diverse provider categories.
7. Add tests that validate the scaffold, not fake provider behavior.
8. Record that real providers are pending.
```

---

## 4. Forbidden

The Agent must not:

```text
pretend a provider works
invent API endpoints
invent credentials
invent rate limits
invent model names as real
mark templates as active
write provider-specific logic in Core
skip the provider architecture because real providers are missing
block the whole project waiting for providers
```

---

## 5. Recommended Directory Structure

If absent, create a structure similar to:

```text
providers/
├── README.md
├── registry/
│   ├── provider_registry_contract.*
│   ├── model_binding_registry_contract.*
│   └── capability_registry_contract.*
├── common/
│   ├── provider_manifest_schema.*
│   ├── provider_contract.*
│   ├── provider_errors.*
│   ├── provider_capabilities.*
│   ├── provider_health.*
│   └── provider_test_harness.*
├── templates/
│   ├── chat_text_provider/
│   ├── reasoning_provider/
│   ├── coding_provider/
│   ├── vision_provider/
│   ├── image_generation_provider/
│   ├── audio_stt_provider/
│   ├── audio_tts_provider/
│   ├── embeddings_provider/
│   ├── rerank_provider/
│   ├── moderation_safety_provider/
│   ├── multimodal_provider/
│   └── provider_agent_provider/
├── real/                               ← added when real providers arrive (see Part II §14)
│   └── <provider_key>/
│       ├── manifest.yaml
│       ├── provider.*
│       ├── config.*
│       ├── runtime/
│       ├── operations/
│       ├── discovery/
│       ├── errors.*
│       └── tests/
└── _pending_real_providers.md
```

Exact language and file extensions depend on the project stack.
If the project chooses a different code layout, the same boundaries must remain.

---

## 6. Diversity Requirement

Even without real providers, the scaffold must account for provider diversity.

Template categories should cover at least:

```text
1. Chat/Text generation
2. Reasoning-heavy model
3. Coding model
4. Vision input model
5. Image generation model
6. Speech-to-text / audio input
7. Text-to-speech / audio output
8. Embeddings
9. Reranking / retrieval support
10. Moderation / safety
11. Multimodal model
12. Provider-native agent / assistant / code agent
```

These are templates only. They must be disabled and clearly marked as non-functional.

---

## 7. Template Manifest Requirements

Every template provider must include a manifest with:

```yaml
id: template_chat_text_provider
name: Template Chat/Text Provider
status: template_disabled
is_template: true
is_functional: false
real_provider_required: true

capabilities:
  chat: true
  reasoning: false
  coding: false
  vision_input: false
  image_generation: false
  audio_input: false
  audio_output: false
  embeddings: false
  rerank: false
  moderation: false
  provider_agent: false

auth:
  types: []

models:
  discovery: not_implemented

notes:
  - This is a scaffold template only.
  - Do not activate without a real provider adapter and contract tests.
```

---

## 8. Provider-Native Agent Template

Because some providers may expose agent-like models, include a disabled template:

```yaml
id: template_provider_agent_provider
name: Template Provider-Native Agent Provider
status: template_disabled
is_template: true
is_functional: false

capabilities:
  provider_agent: true
  tool_use: true
  files: true

agent_module:
  supported: true
  type: provider_agent_template
  state_model: unknown
  supports_provider_tools: unknown
  supports_platform_tools: false
  provider_managed_state: unknown

security:
  provider_side_tools_allowed_by_default: false
  requires_capability_firewall: true
  requires_evaluation: true
  requires_audit: true
```

This template exists only to preserve architecture support for future provider-native agents.

---

## 9. Pending Providers File

Create or maintain:

```text
providers/_pending_real_providers.md
```

Canonical content (merged from both V2 sources):

```md
# Pending Real Providers

No real AI providers are implemented yet.

## Required before activation / before adding any provider
- Choose provider type.
- Real provider API/auth details
- Capability discovery / document capabilities
- Model list or discovery method
- Define operations
- Credential handling
- Rate limit behavior
- Error mapping
- Health checks
- Contract tests
- Security review

## Candidate provider categories
- Chat/Text (API key text/chat)
- Reasoning
- Coding
- OAuth provider
- Session/cookie website provider
- Vision (input)
- Image generation
- Audio STT
- Audio TTS
- Embeddings
- Rerank
- Moderation
- Multimodal
- Provider-native agent
```

---

## 10. Registry Behavior With Templates

Template providers must not appear as active provider candidates.

Router and registry rules:

```text
template_disabled providers are excluded from routing
is_functional=false providers are excluded from execution
real_provider_required=true providers cannot pass health checks
```

The registry may load templates only for schema validation, docs, and scaffolding tests.

---

## 11. Tests Required For Scaffold-Only State

If only scaffold/templates exist, tests should verify:

```text
manifest schema validation
templates are disabled
templates are excluded from routing
templates cannot execute generation
template health check returns non-functional
diverse capability categories are represented
provider contract can be implemented later
Core does not import provider internals
```

Do not write tests that pretend generation works.

---

## 12. Scaffold Must Not Force One Provider Shape

When creating provider scaffolding, do not design templates as if every provider has:

```text
registration
session refresh
account pool
generic generate
chat model
streaming
files
agent behavior
```

The scaffold must be capability-driven.

Templates should show diversity of provider shapes:

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

Each template must mark unsupported modules as not implemented or not applicable, not as TODOs that imply mandatory work.

Example:

```yaml
account_registration:
  required: false
  supported: false
  reason: api_key_provider

session_refresh:
  required: false
  supported: false

generation_operations:
  text_generation: true
  image_generation: false
  embeddings: false
  provider_agent: false
```

The Core should depend on declared capabilities, not on a fixed provider lifecycle.

---

## 13. Interaction With MVP

For MVP, it is acceptable to start with:

```text
Provider framework + templates only
```

if real provider details are not ready.

But MVP cannot claim end-to-end AI execution until at least one real provider is implemented and verified.

---

## 14. Resume Handling During Scaffolding Work

If a session is interrupted while creating provider scaffolding:

```text
1. Resume from Git.
2. Inspect providers/ directory.
3. Inspect templates and manifests.
4. Verify no template is active.
5. Run scaffold validation tests if available.
6. Update progress state.
7. Continue with the smallest missing scaffold piece.
```

If progress state was not updated, reconstruct from:

```text
Git diff
providers/ files
manifest validation
scaffold tests
```

---

## 15. Scaffold-State Final Rule

Missing real providers should not block architecture progress.

```text
No providers yet → build safe diverse scaffold.
Real providers later → implement via contracts.
Never fake provider functionality.
Never contaminate Core with provider-specific shortcuts.
```

---

# PART II — REAL PROVIDER ONBOARDING GUIDE

---

## 16. What Exists Now

The expected current provider work is only:

```text
Provider contracts
Provider manifest schema
Provider registry structure
Capability definitions
Error normalization rules
Health contracts
Disabled provider templates
Pending real providers list
Onboarding guide for future real providers
```

---

## 17. What Must Not Be Claimed Yet

Until at least one real provider is implemented and tested, the project must not claim:

```text
real AI execution works
real chat generation works
real image generation works
real account pool works
real provider auth works
real provider fallback works
real model discovery works
real provider-agent execution works
```

The project may only claim:

```text
provider architecture/scaffold exists
provider contracts exist
provider templates exist
real providers can be added later via the guide
```

---

## 18. Template vs Real Provider

### Template Provider

A template provider is documentation/scaffold only.

```yaml
status: template_disabled
is_template: true
is_functional: false
real_provider_required: true
```

It must be excluded from:

```text
routing
execution
health success
model availability
production use
```

### Real Provider

A real provider is an implemented and verified integration.

```yaml
status: active | disabled | maintenance
is_template: false
is_functional: true
real_provider_required: false
```

It may be used only after passing required contract/security tests.

---

## 19. Universal Real Provider Onboarding Checklist

For every real provider, regardless of type:

```text
1. Identify provider type and auth method.
2. Document real capabilities.
3. Create real manifest.
4. Implement only declared operations.
5. Implement credential handling without plaintext secrets.
6. Implement health check.
7. Implement error normalization.
8. Implement rate/limit behavior if known.
9. Add contract tests for each declared capability.
10. Add security checks for secrets and tenant isolation.
11. Register provider in Provider Registry.
12. Register model/provider bindings if models exist.
13. Keep provider disabled until tests pass.
14. Enable via Admin/Config only after verification.
```

---

## 20. Provider Type Reference Patterns

The following examples are not real providers. They are reference patterns for adding real providers later.

---

### Type A — API Key Text/Chat Provider

#### When to use

Provider exposes a normal API key and text/chat generation endpoint.

#### Usually Needs

```text
api_key_validation
text_generation
model discovery or static model bindings
error normalization
basic health check
```

#### Usually Does Not Need

```text
account registration
session refresh
account pool
cookies
browser automation
provider-native agent
```

#### Example Manifest

```yaml
id: real_text_api_provider
name: Real Text API Provider
status: disabled
is_template: false
is_functional: false

auth:
  types:
    - api_key
  secret_storage: secret_manager

capabilities:
  chat: true
  text_generation: true
  streaming: true
  vision_input: false
  image_generation: false
  embeddings: false
  provider_agent: false

operations:
  generate_text: true

models:
  discovery: static_or_dynamic

account_pool:
  required: false
```

#### Required Tests

```text
api key validation
text generation contract
streaming if declared
rate limit error mapping
secret redaction
provider unavailable handling
```

---

### Type B — OAuth Provider

#### When to use

Provider requires OAuth authorization and refresh tokens.

#### Usually Needs

```text
oauth_flow
credential refresh
token expiry handling
user-owned credentials support
health check
```

#### Example Manifest

```yaml
id: real_oauth_provider
name: Real OAuth Provider
status: disabled

auth:
  types:
    - oauth
  supports_refresh: true

credential_lifecycle:
  access_token: true
  refresh_token: true
  expiry: true

capabilities:
  chat: true
  file_upload: true
```

#### Required Tests

```text
oauth callback validation
refresh token flow
expired token handling
revoked credential handling
credential_ref only in DB
no token in logs
```

---

### Type C — Session/Cookie Website Provider

#### When to use

Provider behaves like a website/session-based service.

#### Usually Needs

```text
login/authenticate
session handling
cookies
csrf if applicable
session refresh
account validation
possibly account pool
provider-specific request runtime
```

#### Example Manifest

```yaml
id: real_session_provider
name: Real Session Provider
status: disabled

auth:
  types:
    - session_cookie
  supports_refresh: true

runtime:
  session_required: true
  csrf_required: unknown
  polling_required: unknown

account_pool:
  required: true
  lease_required: true

capabilities:
  chat: true
  file_upload: true
```

#### Required Tests

```text
session validation
session refresh
cookie secret storage
csrf handling if used
account lease
cooldown handling
rate limit response mapping
provider health degradation
```

#### Security Notes

Do not build CAPTCHA bypass or anti-abuse circumvention.

If verification is required, represent it as:

```text
VERIFICATION_REQUIRED
PENDING_OPERATOR_ACTION
```

---

### Type D — Image Generation Provider

#### When to use

Provider mainly generates images.

#### Usually Needs

```text
generate_image
asset result handling
async job polling sometimes
moderation/safety errors
cost tracking per image
```

#### Usually Does Not Need

```text
chat generation
embeddings
rerank
account pool unless provider-specific limits require it
```

#### Example Manifest

```yaml
id: real_image_provider
name: Real Image Provider
status: disabled

capabilities:
  image_generation: true
  text_generation: false
  vision_input: false

operations:
  generate_image: true

assets:
  output_images: true
  download_required: true

runtime:
  async_jobs: true
  polling: true
```

#### Required Tests

```text
image request schema
async job polling
image result asset storage
content rejected mapping
cost accounting
```

---

### Type E — Vision / Image Input Provider

#### When to use

Provider analyzes images or accepts image input.

#### Usually Needs

```text
file/image upload
vision analysis
input size validation
asset handling
```

#### Example Manifest

```yaml
id: real_vision_provider
name: Real Vision Provider
status: disabled

capabilities:
  vision_input: true
  text_generation: true
  image_generation: false

operations:
  analyze_vision: true
  generate_text: true

assets:
  upload_image: true
```

#### Required Tests

```text
image upload
unsupported file rejection
vision response normalization
file size limits
secret-free evidence storage
```

---

### Type F — Embeddings Provider

#### When to use

Provider only creates embeddings.

#### Usually Needs

```text
create_embeddings
batch support maybe
model binding
vector dimension metadata
```

#### Usually Does Not Need

```text
chat
image generation
account pool
provider-agent
```

#### Example Manifest

```yaml
id: real_embeddings_provider
name: Real Embeddings Provider
status: disabled

capabilities:
  embeddings: true
  chat: false
  text_generation: false

operations:
  create_embeddings: true

embedding_metadata:
  dimensions: unknown_until_real_provider
  supports_batch: unknown
```

#### Required Tests

```text
embedding vector shape
batch behavior
input length errors
model dimension metadata
```

---

### Type G — Rerank Provider

#### When to use

Provider scores/reranks documents for retrieval.

#### Usually Needs

```text
rerank_documents
score normalization
input document limits
```

#### Example Manifest

```yaml
id: real_rerank_provider
name: Real Rerank Provider
status: disabled

capabilities:
  rerank: true

operations:
  rerank_documents: true
```

#### Required Tests

```text
ranking order
score normalization
document limit handling
empty input handling
```

---

### Type H — Audio STT Provider

#### When to use

Provider transcribes audio to text.

#### Usually Needs

```text
audio upload
transcribe_audio
file duration limits
format validation
```

#### Example Manifest

```yaml
id: real_audio_stt_provider
name: Real Audio STT Provider
status: disabled

capabilities:
  audio_input: true
  speech_to_text: true

operations:
  transcribe_audio: true

assets:
  upload_audio: true
```

#### Required Tests

```text
audio upload
format rejection
transcription result normalization
duration limit mapping
```

---

### Type I — Audio TTS Provider

#### When to use

Provider synthesizes speech/audio.

#### Usually Needs

```text
synthesize_speech
voice metadata
output audio asset handling
```

#### Example Manifest

```yaml
id: real_audio_tts_provider
name: Real Audio TTS Provider
status: disabled

capabilities:
  audio_output: true
  text_to_speech: true

operations:
  synthesize_speech: true

assets:
  output_audio: true
```

#### Required Tests

```text
voice selection
text length limit
output audio storage
provider error mapping
```

---

### Type J — Moderation / Safety Provider

#### When to use

Provider only classifies content safety.

#### Usually Needs

```text
moderate_content
category mapping
confidence/score normalization
```

#### Example Manifest

```yaml
id: real_moderation_provider
name: Real Moderation Provider
status: disabled

capabilities:
  moderation: true

operations:
  moderate_content: true
```

#### Required Tests

```text
category mapping
confidence score normalization
safe/unsafe decision contract
```

---

### Type K — Multimodal Provider

#### When to use

Provider supports several modalities.

#### Usually Needs

```text
text_generation
vision_input
file upload
maybe audio/image capabilities
operation-level limits
```

#### Example Manifest

```yaml
id: real_multimodal_provider
name: Real Multimodal Provider
status: disabled

capabilities:
  text_generation: true
  vision_input: true
  file_upload: true
  image_generation: false
  audio_input: false
  provider_agent: false

operations:
  generate_text: true
  analyze_vision: true
  upload_asset: true
```

#### Required Tests

```text
text-only request
image-input request
mixed input request
unsupported modality rejection
operation-specific limits
```

---

### Type L — Provider-Native Agent Provider

#### When to use

Provider exposes agent-like behavior:

```text
assistant API
code agent
research agent
tool-using model
managed thread/run
```

#### Usually Needs

```text
run_provider_agent
provider-managed run/thread state
event normalization
strict tool policy
trace/audit support
evaluation requirement
```

#### Example Manifest

```yaml
id: real_provider_agent_provider
name: Real Provider Agent Provider
status: disabled

capabilities:
  provider_agent: true
  tool_use: true
  files: true

operations:
  run_provider_agent: true

agent_module:
  supported: true
  type: managed_assistant_or_code_agent
  state_model: thread_run_or_session
  provider_managed_state: true
  supports_provider_tools: unknown
  supports_platform_tools: false

security:
  provider_side_tools_allowed_by_default: false
  requires_capability_firewall: true
  requires_audit: true
  requires_evaluation: true
```

#### Required Tests

```text
agent run lifecycle
event normalization
tool request blocking
provider-managed state tenant scoping
cancellation
usage accounting
evaluation before final response
```

---

## 21. Activation Requirements — Template → Real Provider

A template can become a real provider only after:

```text
real manifest completed
adapter implemented
auth/credential handling implemented
model discovery or static bindings implemented
generation implemented where applicable
error normalization implemented
health checks implemented
contract tests pass
security review completed
admin enablement configured
```

Then status may change from:

```text
template_disabled
```

to:

```text
active | disabled | maintenance
```

---

## 22. Real Provider Activation Checklist

A provider can be enabled only when:

```text
manifest is real, not template
capabilities are verified
credential handling is secure
operations implemented only for declared capabilities
contract tests pass
health check works
errors are normalized
rate/limit behavior handled
secrets are not logged
admin config enables provider
router sees provider as eligible only when healthy
```

---

## 23. Final Rule

Until a real provider is implemented:

```text
Examples are examples.
Templates are templates.
Scaffold is scaffold.
No real execution is claimed.
```

When adding a real provider:

```text
declare real capabilities
implement only those capabilities
verify with contract tests
keep Core provider-agnostic
activate only after admin/security approval
```

---

## 24. Traceability (V2 → V3)

```text
v2 23 §1–§4   → Part I §1–§4 (purpose/current state, core rule, required behavior, forbidden)
v2 23 §5      → Part I §5 (directory structure; merged with v2 25 §5 real/ layout)
v2 23 §6–§8   → Part I §6–§8 (diversity, template manifest, provider-agent template)
v2 23 §9      → Part I §9 (pending providers file; merged with v2 25 §9 example)
v2 23 §10–§11 → Part I §10–§11 (registry behavior, scaffold tests)
v2 23 §12     → Part II §21 (activation requirements)
v2 23 §13–§15 → Part I §13–§15 (MVP interaction, resume handling, final rule)
v2 23 §16     → Part I §12 (no forced provider shape)
v2 23 §17     → absorbed (pointer to v2 25; both sources now merged here)
v2 25 §1      → Part I §1 (current state statement)
v2 25 §2–§4   → Part II §16–§18 (what exists, what must not be claimed, template vs real)
v2 25 §5      → Part I §5 (real/ directory layout merged into structure)
v2 25 §6      → Part II §19 (universal onboarding checklist)
v2 25 §7 A–L  → Part II §20 Types A–L (all 12 provider type patterns, verbatim)
v2 25 §8      → Part II §22 (activation checklist)
v2 25 §9      → Part I §9 (pending providers example merged)
v2 25 §10     → Part II §23 (final rule)
No decision, rule, manifest field, test requirement, or security constraint was dropped or changed.
```

