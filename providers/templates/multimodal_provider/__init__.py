"""Template 11/12 — Multimodal provider (31 §6 cat. 11).

Shape represented (31 §12): session/cookie website provider with an account
pool — the hardest lifecycle shape. Declares multiple modalities (text,
vision, image, files). Proves the scaffold supports multi-capability
providers WITHOUT forcing that shape on the others. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_multimodal_provider",
    name="Template Multimodal Provider",
    capabilities=ProviderCapabilities(
        chat=True,
        vision_input=True,
        image_generation=True,
        file_upload=True,
    ),
    operations=[
        ProviderOperation.GENERATE_TEXT,
        ProviderOperation.ANALYZE_VISION,
        ProviderOperation.GENERATE_IMAGE,
        ProviderOperation.UPLOAD_ASSET,
        ProviderOperation.DOWNLOAD_ASSET,
    ],
    intended_auth_shape="session_cookie",
    account_pool_supported=True,
    extra_notes=(
        "Multimodal shape: multiple modalities in one provider (31 §12).",
        "Account-pool supported: session/cookie providers rotate accounts (30 §10).",
    ),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
