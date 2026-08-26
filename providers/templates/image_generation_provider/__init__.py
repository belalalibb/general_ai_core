"""Template 5/12 — Image generation provider (31 §6 cat. 5).

Shape represented (31 §12): image-ONLY provider — no chat, no text. Proves
the scaffold does not assume every provider has a chat model. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_image_generation_provider",
    name="Template Image Generation Provider",
    capabilities=ProviderCapabilities(image_generation=True),
    operations=[ProviderOperation.GENERATE_IMAGE, ProviderOperation.DOWNLOAD_ASSET],
    intended_auth_shape="api_key",
    extra_notes=("Image-only shape: no chat/text capability by design (31 §12).",),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
