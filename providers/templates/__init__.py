"""Scaffold template providers (31 §5–§8, T-IMPL-020) — ALL disabled.

12 diverse, non-functional templates covering the 31 §6 diversity categories:

 1. chat_text_provider          — Chat/Text generation        (api_key shape)
 2. reasoning_provider          — Reasoning-heavy model       (oauth shape)
 3. coding_provider             — Coding model                (api_key shape)
 4. vision_provider             — Vision input model          (api_key shape)
 5. image_generation_provider   — Image generation (image-only)
 6. audio_stt_provider          — Speech-to-text / audio input
 7. audio_tts_provider          — Text-to-speech / audio output
 8. embeddings_provider         — Embeddings (embeddings-only, no-auth local)
 9. rerank_provider             — Reranking / retrieval support
10. moderation_safety_provider  — Moderation / safety (no-auth local)
11. multimodal_provider         — Multimodal (session/cookie shape, pool)
12. provider_agent_provider     — Provider-native agent (31 §8)

31 §12: the set deliberately spans api_key / oauth / session_cookie /
no-auth-local shapes and text-only / image-only / embeddings-only /
moderation-only / multimodal / agent capability shapes — the scaffold must
not force one provider shape.

``all_template_manifests()`` is the single enumeration the scaffold tests
(31 §11) and docs use; adding a template means adding it here explicitly.
"""

from __future__ import annotations

from core.contracts.provider import ProviderManifest

from providers.templates import (
    audio_stt_provider,
    audio_tts_provider,
    chat_text_provider,
    coding_provider,
    embeddings_provider,
    image_generation_provider,
    moderation_safety_provider,
    multimodal_provider,
    provider_agent_provider,
    reasoning_provider,
    rerank_provider,
    vision_provider,
)

#: 31 §6 category number -> template module (explicit, closed enumeration).
TEMPLATE_MODULES = (
    chat_text_provider,
    reasoning_provider,
    coding_provider,
    vision_provider,
    image_generation_provider,
    audio_stt_provider,
    audio_tts_provider,
    embeddings_provider,
    rerank_provider,
    moderation_safety_provider,
    multimodal_provider,
    provider_agent_provider,
)


def all_template_manifests() -> list[ProviderManifest]:
    """Return every scaffold template manifest (order = 31 §6 categories)."""
    return [module.MANIFEST for module in TEMPLATE_MODULES]
