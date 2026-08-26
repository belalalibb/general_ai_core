"""Template 4/12 — Vision input model provider (31 §6 cat. 4).

Shape represented (31 §12): API-key provider with vision input + file upload.
Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation

from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_vision_provider",
    name="Template Vision Provider",
    capabilities=ProviderCapabilities(vision_input=True, file_upload=True),
    operations=[ProviderOperation.ANALYZE_VISION, ProviderOperation.UPLOAD_ASSET],
    intended_auth_shape="api_key",
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
