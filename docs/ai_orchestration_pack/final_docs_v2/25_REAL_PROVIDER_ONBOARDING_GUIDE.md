# 25 — Real Provider Onboarding Guide
## Current State, Examples, and How to Add Real Providers Later

---

## 1. Current State — Important

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

## 2. What Exists Now

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

## 3. What Must Not Be Claimed Yet

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

## 4. Template vs Real Provider

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

## 5. Where Real Providers Should Live

Recommended structure:

```text
providers/
├── common/
├── registry/
├── templates/
├── real/
│   ├── <provider_key>/
│   │   ├── manifest.yaml
│   │   ├── provider.*
│   │   ├── config.*
│   │   ├── runtime/
│   │   ├── operations/
│   │   ├── discovery/
│   │   ├── errors.*
│   │   └── tests/
└── _pending_real_providers.md
```

If the project chooses a different code layout, the same boundaries must remain.

---

## 6. Universal Real Provider Onboarding Checklist

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

## 7. Provider Type Examples

The following examples are not real providers. They are reference patterns for adding real providers later.

---

# Type A — API Key Text/Chat Provider

## When to use

Provider exposes a normal API key and text/chat generation endpoint.

## Usually Needs

```text
api_key_validation
text_generation
model discovery or static model bindings
error normalization
basic health check
```

## Usually Does Not Need

```text
account registration
session refresh
account pool
cookies
browser automation
provider-native agent
```

## Example Manifest

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

## Required Tests

```text
api key validation
text generation contract
streaming if declared
rate limit error mapping
secret redaction
provider unavailable handling
```

---

# Type B — OAuth Provider

## When to use

Provider requires OAuth authorization and refresh tokens.

## Usually Needs

```text
oauth_flow
credential refresh
token expiry handling
user-owned credentials support
health check
```

## Example Manifest

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

## Required Tests

```text
oauth callback validation
refresh token flow
expired token handling
revoked credential handling
credential_ref only in DB
no token in logs
```

---

# Type C — Session/Cookie Website Provider

## When to use

Provider behaves like a website/session-based service.

## Usually Needs

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

## Example Manifest

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

## Required Tests

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

## Security Notes

Do not build CAPTCHA bypass or anti-abuse circumvention.

If verification is required, represent it as:

```text
VERIFICATION_REQUIRED
PENDING_OPERATOR_ACTION
```

---

# Type D — Image Generation Provider

## When to use

Provider mainly generates images.

## Usually Needs

```text
generate_image
asset result handling
async job polling sometimes
moderation/safety errors
cost tracking per image
```

## Usually Does Not Need

```text
chat generation
embeddings
rerank
account pool unless provider-specific limits require it
```

## Example Manifest

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

## Required Tests

```text
image request schema
async job polling
image result asset storage
content rejected mapping
cost accounting
```

---

# Type E — Vision / Image Input Provider

## When to use

Provider analyzes images or accepts image input.

## Usually Needs

```text
file/image upload
vision analysis
input size validation
asset handling
```

## Example Manifest

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

## Required Tests

```text
image upload
unsupported file rejection
vision response normalization
file size limits
secret-free evidence storage
```

---

# Type F — Embeddings Provider

## When to use

Provider only creates embeddings.

## Usually Needs

```text
create_embeddings
batch support maybe
model binding
vector dimension metadata
```

## Usually Does Not Need

```text
chat
image generation
account pool
provider-agent
```

## Example Manifest

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

## Required Tests

```text
embedding vector shape
batch behavior
input length errors
model dimension metadata
```

---

# Type G — Rerank Provider

## When to use

Provider scores/reranks documents for retrieval.

## Usually Needs

```text
rerank_documents
score normalization
input document limits
```

## Example Manifest

```yaml
id: real_rerank_provider
name: Real Rerank Provider
status: disabled

capabilities:
  rerank: true

operations:
  rerank_documents: true
```

## Required Tests

```text
ranking order
score normalization
document limit handling
empty input handling
```

---

# Type H — Audio STT Provider

## When to use

Provider transcribes audio to text.

## Usually Needs

```text
audio upload
transcribe_audio
file duration limits
format validation
```

## Example Manifest

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

## Required Tests

```text
audio upload
format rejection
transcription result normalization
duration limit mapping
```

---

# Type I — Audio TTS Provider

## When to use

Provider synthesizes speech/audio.

## Usually Needs

```text
synthesize_speech
voice metadata
output audio asset handling
```

## Example Manifest

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

## Required Tests

```text
voice selection
text length limit
output audio storage
provider error mapping
```

---

# Type J — Moderation / Safety Provider

## When to use

Provider only classifies content safety.

## Usually Needs

```text
moderate_content
category mapping
confidence/score normalization
```

## Example Manifest

```yaml
id: real_moderation_provider
name: Real Moderation Provider
status: disabled

capabilities:
  moderation: true

operations:
  moderate_content: true
```

## Required Tests

```text
category mapping
confidence score normalization
safe/unsafe decision contract
```

---

# Type K — Multimodal Provider

## When to use

Provider supports several modalities.

## Usually Needs

```text
text_generation
vision_input
file upload
maybe audio/image capabilities
operation-level limits
```

## Example Manifest

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

## Required Tests

```text
text-only request
image-input request
mixed input request
unsupported modality rejection
operation-specific limits
```

---

# Type L — Provider-Native Agent Provider

## When to use

Provider exposes agent-like behavior:

```text
assistant API
code agent
research agent
tool-using model
managed thread/run
```

## Usually Needs

```text
run_provider_agent
provider-managed run/thread state
event normalization
strict tool policy
trace/audit support
evaluation requirement
```

## Example Manifest

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

## Required Tests

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

## 8. Real Provider Activation Checklist

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

## 9. Example `_pending_real_providers.md`

```md
# Pending Real Providers

No real AI providers are implemented yet.

## Before adding any provider
- Choose provider type.
- Collect real API/auth details.
- Document capabilities.
- Define operations.
- Define credential handling.
- Define rate limits.
- Define error mapping.
- Write contract tests.

## Candidate provider categories
- API key text/chat
- OAuth provider
- Session/cookie website provider
- Image generation
- Vision input
- Embeddings
- Rerank
- Audio STT
- Audio TTS
- Moderation
- Multimodal
- Provider-native agent
```

---

## 10. Final Rule

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
