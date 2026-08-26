"""Template 6/12 — Speech-to-text / audio input provider (31 §6 cat. 6).

Shape represented (31 §12): API-key audio-input provider. Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import ProviderCapabilities, ProviderOperation

from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_audio_stt_provider",
    name="Template Audio STT Provider",
    capabilities=ProviderCapabilities(audio_input=True, file_upload=True),
    operations=[ProviderOperation.TRANSCRIBE_AUDIO, ProviderOperation.UPLOAD_ASSET],
    intended_auth_shape="api_key",
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
