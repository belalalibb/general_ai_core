# Pending Real Providers

## Implemented real providers

- **groq** (`providers/real/groq/`, T-IMPL-036, 2026-08-28) — OpenAI-compatible
  API-key chat/text provider (31 §20 Type A). Operations: `generate_text`.
  Verified LIVE at onboarding: credential validation (ACTIVE), provider
  health (HEALTHY), dynamic model discovery (14 models), end-to-end
  generation through POST /v1/execute → Router → ExecutionService →
  GroqAdapter → api.groq.com with usage settlement. Hermetic contract
  suite: `tests/providers/test_groq_adapter.py` (MockTransport, no network
  in gates). Live suites (env-gated, manual): `test_groq_live.py`,
  `test_groq_live_e2e.py` — skipped unless `GROQ_API_KEY` is set.
  Manifest ships `status: disabled` (31 §19 step 13); enablement is a
  composition/admin decision after verification (step 14). The credential
  enters ONLY via `SecretManagerPort` → opaque `credential_ref` (20 §5);
  no secret material exists anywhere in the repo.

- **genspark_llm** (`providers/real/genspark_llm/`, T-IMPL-037, 2026-08-28) —
  OpenAI-compatible API-key chat/text provider (31 §20 Type A) over the
  Genspark LLM proxy (an aggregation gateway exposing many upstream model
  families — GPT/Claude/DeepSeek/Kimi/Grok/etc. — behind ONE key; modeled
  as ONE Type A provider per 30 §4). Operations: `generate_text`.
  Verified LIVE at onboarding: credential validation (ACTIVE), provider
  health (HEALTHY), dynamic model discovery (52 models), the structural
  model-allowlist rejection mapping (HTTP 400 → model_unavailable), and
  end-to-end generation through POST /v1/execute → Router →
  ExecutionService → GensparkLLMAdapter → live proxy with usage settlement.
  Hermetic contract suite: `tests/providers/test_genspark_llm_adapter.py`
  (MockTransport, no network in gates). Live suites (env-gated, manual):
  `test_genspark_llm_live.py`, `test_genspark_llm_live_e2e.py` — skipped
  unless `GSK_API_KEY` is set. Manifest ships `status: disabled` (31 §19
  step 13); enablement is a composition/admin decision after verification
  (step 14). The credential enters ONLY via `SecretManagerPort` → opaque
  `credential_ref` (20 §5); no secret material exists anywhere in the repo.

The 41 §49 closing rule — "end-to-end AI execution is not considered
complete until at least one real provider is implemented and verified" —
is **SATISFIED** by groq as of T-IMPL-036 (and independently re-proven by
genspark_llm at T-IMPL-037).

## Still-pending scaffold state (remaining categories)

The 12 templates under `providers/templates/` remain disabled scaffolds
(`status: template_disabled`, `is_functional: false`,
`real_provider_required: true`) and are excluded from routing, execution,
and health passing (31 §10). Every category other than Chat/Text remains
NOT-CLAIMED.

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

## What cannot be claimed until MORE real providers land (41 §49)

Claimed for **text generation via groq and genspark_llm only** (both
verified 2026-08-28): real credential validation, real model discovery,
real error/rate-limit mapping, passing provider health checks, end-to-end
Router execution.

Still NOT-CLAIMED for every other category:

- Real image/audio/embeddings/rerank/moderation/vision/agent generation
- OAuth or session/cookie provider auth shapes
- Account-pool lifecycle against a real provider

Real provider onboarding follows 31 Part II (§14+): each real provider lands
under `providers/real/<provider_key>/` with its own manifest, adapter,
contract tests, and security review — never by activating a template.
