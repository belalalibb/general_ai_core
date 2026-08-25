# 23 — AI Providers Scaffolding Policy
## When No Real `ai_providers` Exist Yet

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-004)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

---

## 1. Purpose

This policy defines what the Agent must do when the project does not yet contain real AI provider implementations.

The goal is to avoid blocking the architecture while also avoiding fake, invented, or misleading provider integrations.

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
└── _pending_real_providers.md
```

Exact language and file extensions depend on the project stack.

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

It should list:

```md
# Pending Real Providers

No real providers are implemented yet.

## Required before activation
- Real provider API/auth details
- Capability discovery
- Model list or discovery method
- Credential handling
- Rate limit behavior
- Error mapping
- Health checks
- Contract tests
- Security review

## Candidate Categories
- Chat/Text
- Reasoning
- Coding
- Vision
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

## 12. Activation Requirements For Real Provider

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

## 13. Interaction With MVP

For MVP, it is acceptable to start with:

```text
Provider framework + templates only
```

if real provider details are not ready.

But MVP cannot claim end-to-end AI execution until at least one real provider is implemented and verified.

---

## 14. Resume Handling

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

## 15. Final Rule

Missing real providers should not block architecture progress.

```text
No providers yet → build safe diverse scaffold.
Real providers later → implement via contracts.
Never fake provider functionality.
Never contaminate Core with provider-specific shortcuts.
```

---

## 16. Scaffold Must Not Force One Provider Shape

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

## 17. Real Provider Onboarding Reference

This document defines what to do when no real providers exist.

For the practical guide to adding real providers later by provider type, use:

```text
25_REAL_PROVIDER_ONBOARDING_GUIDE.md
```

That guide explicitly states that the current repository has no real providers yet and that all examples/templates are non-functional until implemented and tested.
