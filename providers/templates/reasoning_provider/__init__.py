"""Template 2/12 — Reasoning-heavy model provider (31 §6 cat. 2).

Shape represented (31 §12): OAuth provider, text/reasoning. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation

from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_reasoning_provider",
    name="Template Reasoning Provider",
    capabilities=ProviderCapabilities(chat=True, reasoning=True),
    operations=[ProviderOperation.GENERATE_TEXT],
    intended_auth_shape="oauth",
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
