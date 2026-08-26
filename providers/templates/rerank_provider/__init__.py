"""Template 9/12 — Reranking / retrieval support provider (31 §6 cat. 9).

Shape represented (31 §12): API-key, rerank-ONLY retrieval-support provider.
Proves the scaffold supports single-purpose non-generative providers.
Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_rerank_provider",
    name="Template Rerank Provider",
    capabilities=ProviderCapabilities(rerank=True),
    operations=[ProviderOperation.RERANK_DOCUMENTS],
    intended_auth_shape="api_key",
    extra_notes=("Rerank-only shape: retrieval support, no generation (31 §12).",),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
