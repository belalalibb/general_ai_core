"""Template 8/12 — Embeddings provider (31 §6 cat. 8).

Shape represented (31 §12): no-auth LOCAL/internal, embeddings-ONLY provider.
Proves the scaffold supports providers with no auth and a single capability.
Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation

from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_embeddings_provider",
    name="Template Embeddings Provider",
    capabilities=ProviderCapabilities(embeddings=True),
    operations=[ProviderOperation.CREATE_EMBEDDINGS],
    intended_auth_shape="no-auth local/internal",
    extra_notes=("Embeddings-only shape: no generation capability (31 §12).",),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
