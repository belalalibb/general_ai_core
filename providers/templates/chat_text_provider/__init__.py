"""Template 1/12 — Chat/Text generation provider (31 §6 cat. 1, §7 example).

Shape represented (31 §12): API-key, text-only provider. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation

from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_chat_text_provider",
    name="Template Chat/Text Provider",
    capabilities=ProviderCapabilities(chat=True),
    operations=[ProviderOperation.GENERATE_TEXT],
    intended_auth_shape="api_key",
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
