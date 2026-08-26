# Pending Real Providers

No real AI providers are implemented yet.

This ledger is the scaffold-state truth record required by 31 §9 and 41 §49:
end-to-end AI execution with real providers is explicitly **NOT-CLAIMED**.
The 12 templates under `providers/templates/` are disabled scaffolds
(`status: template_disabled`, `is_functional: false`,
`real_provider_required: true`) and are excluded from routing, execution,
and health passing (31 §10).

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

## What cannot be claimed until real providers land (41 §49)

- Real provider generation of any kind (text/image/audio/embeddings/…)
- Real credential validation against a provider
- Real model discovery from a provider API
- Real rate-limit observation or error mapping from provider responses
- Provider health checks that PASS
- End-to-end execution through the Router with a live provider

Real provider onboarding follows 31 Part II (§14+): each real provider lands
under `providers/real/<provider_key>/` with its own manifest, adapter,
contract tests, and security review — never by activating a template.
