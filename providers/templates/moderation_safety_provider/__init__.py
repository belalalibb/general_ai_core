"""Template 10/12 — Moderation / safety provider (31 §6 cat. 10).

Shape represented (31 §12): no-auth LOCAL/internal, moderation-ONLY provider.
Proves the scaffold supports safety-classification providers that never
generate content. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_moderation_safety_provider",
    name="Template Moderation/Safety Provider",
    capabilities=ProviderCapabilities(moderation=True),
    operations=[ProviderOperation.MODERATE_CONTENT],
    intended_auth_shape="no-auth local/internal",
    extra_notes=("Moderation-only shape: classification, never generation (31 §12).",),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
