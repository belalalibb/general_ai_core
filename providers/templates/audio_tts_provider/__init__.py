"""Template 7/12 — Text-to-speech / audio output provider (31 §6 cat. 7).

Shape represented (31 §12): API-key audio-output provider. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_audio_tts_provider",
    name="Template Audio TTS Provider",
    capabilities=ProviderCapabilities(audio_output=True),
    operations=[ProviderOperation.SYNTHESIZE_SPEECH, ProviderOperation.DOWNLOAD_ASSET],
    intended_auth_shape="api_key",
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
