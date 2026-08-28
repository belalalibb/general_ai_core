"""Groq — the FIRST real provider (T-IMPL-036; 31 §19/§20 Type A).

Real manifest (NOT a template): ``is_template=false``, ``is_functional=true``,
``real_provider_required=false`` — but ``status="disabled"`` per 31 §19
step 13: a real provider stays DISABLED until its contract tests pass and
it is enabled via Admin/Config (step 14). The composition root flips the
domain ``ProviderStatus`` only after verification.

Credential posture (20 §5): this package contains NO secret material and
no environment reads. The API key enters only through the composition
root: stored in a ``SecretManagerPort`` -> opaque credential_ref ->
resolved inside the adapter at the last moment.

Models: discovery is dynamic (GET /models). ``static_models`` lists the
model names VERIFIED against the live endpoint at onboarding time
(2026-08-28) so registry bindings can be created without a network call;
they are provider-declared names, not invented ones (41 §49).
"""

from __future__ import annotations

from core.contracts.domain import AuthType
from core.contracts.provider import (
    ManifestAccountPool,
    ManifestAuth,
    ManifestErrors,
    ManifestHealth,
    ManifestModels,
    ManifestRateLimits,
    ProviderCapabilities,
    ProviderManifest,
    ProviderOperation,
)
from providers.real.groq.adapter import GROQ_BASE_URL, GroqAdapter

__all__ = ["GROQ_BASE_URL", "MANIFEST", "GroqAdapter"]

#: Model names verified against GET /models on 2026-08-28 (text-generation
#: capable subset; whisper/tts/guard models are omitted because this
#: manifest declares generate_text only — 30 §5: undeclared = ineligible).
VERIFIED_TEXT_MODELS: tuple[str, ...] = (
    "allam-2-7b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.6-27b",
    "qwen/qwen3.8-27b",
)

MANIFEST = ProviderManifest(
    id="groq",
    name="Groq",
    version="1.0.0",
    status="disabled",  # 31 §19 step 13: disabled until tests pass; enabled via admin
    is_template=False,
    is_functional=True,
    real_provider_required=False,
    auth=ManifestAuth(types=[AuthType.API_KEY], supports_refresh=False),
    account_pool=ManifestAccountPool(supported=False),
    capabilities=ProviderCapabilities(chat=True, reasoning=True, code=True),
    operations=[ProviderOperation.GENERATE_TEXT],
    models=ManifestModels(discovery="dynamic", static_models=list(VERIFIED_TEXT_MODELS)),
    rate_limits=ManifestRateLimits(strategy="provider_defined"),
    health=ManifestHealth(checks=["models_endpoint_authenticated"]),
    errors=ManifestErrors(mapping="providers/real/groq/adapter.py:_normalize_http_response"),
    notes=[
        "Real provider (31 §19). OpenAI-compatible endpoint: " + GROQ_BASE_URL,
        "Credential enters via SecretManagerPort only; adapter resolves at last moment.",
        "Audio (whisper/tts) and moderation models exist at the provider but are "
        "NOT declared here: this manifest covers generate_text only (30 §5).",
    ],
)
