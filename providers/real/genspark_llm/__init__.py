"""Genspark LLM Proxy — the SECOND real provider (T-IMPL-037; 31 §19/§20 Type A).

Real manifest (NOT a template): ``is_template=false``, ``is_functional=true``,
``real_provider_required=false`` — but ``status="disabled"`` per 31 §19
step 13: a real provider stays DISABLED until its contract tests pass and
it is enabled via Admin/Config (step 14). The composition root flips the
domain ``ProviderStatus`` only after verification.

Credential posture (20 §5): this package contains NO secret material and
no environment reads. The API key enters only through the composition
root: stored in a ``SecretManagerPort`` -> opaque credential_ref ->
resolved inside the adapter at the last moment.

Models: discovery is dynamic (GET /models). ``static_models`` lists a
representative subset of the model names VERIFIED against the live
endpoint at onboarding time (2026-08-28; 52 models total were returned)
so registry bindings can be created without a network call; they are
provider-declared names, not invented ones (41 §49). The proxy is an
aggregation gateway (OpenAI/Anthropic/DeepSeek/etc. families behind ONE
API-key auth + OpenAI-compatible surface) — under 30 §4 the platform
models what it can DO, so it is one Type A provider, not many.
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
from providers.real.genspark_llm.adapter import GENSPARK_LLM_BASE_URL, GensparkLLMAdapter

__all__ = ["GENSPARK_LLM_BASE_URL", "MANIFEST", "GensparkLLMAdapter"]

#: Model names verified against GET /models on 2026-08-28 (representative
#: text-generation subset of the 52 returned; all families are chat/text).
VERIFIED_TEXT_MODELS: tuple[str, ...] = (
    "gpt-5-nano",
    "gpt-5-mini",
    "gpt-5.2",
    "claude-sonnet-4-5",
    "claude-opus-4-5",
    "deep-seek-v4-flash",
    "kimi-k3",
    "grok-4.6",
)

MANIFEST = ProviderManifest(
    id="genspark_llm",
    name="Genspark LLM Proxy",
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
    errors=ManifestErrors(
        mapping="providers/real/genspark_llm/adapter.py:_normalize_http_response"
    ),
    notes=[
        "Real provider (31 §19). OpenAI-compatible endpoint: " + GENSPARK_LLM_BASE_URL,
        "Credential enters via SecretManagerPort only; adapter resolves at last moment.",
        "Aggregation gateway: many upstream model families behind one API key; "
        "modeled as ONE Type A provider per 30 §4 (capability-driven).",
        "Model-allowlist rejections arrive as HTTP 400 'Model ... is not allowed' "
        "(live-verified) and are normalized to model_unavailable structurally.",
    ],
)
