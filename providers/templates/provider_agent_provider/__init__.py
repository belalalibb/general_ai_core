"""Template 12/12 — Provider-native agent provider (31 §6 cat. 12, §8).

Shape represented (31 §12): OAuth provider exposing an agent-like model.
Carries the 31 §8 ``agent_module`` and ``security`` blocks verbatim:
provider-managed behaviors are ``unknown`` (never assumed supported, 11 §5),
provider-side tools are DENIED by default, and capability-firewall /
evaluation / audit are all required.

This template exists ONLY to preserve architecture support for future
provider-native agents (31 §8). Critical rule preserved: Provider Agent
Capability != Platform Agent Runtime — the platform remains the commander.
Non-functional.
"""

from __future__ import annotations

from core.contracts.provider import (
    ManifestAgentModule,
    ManifestSecurity,
    ProviderCapabilities,
    ProviderOperation,
)
from providers.common.manifest_builder import build_template_manifest
from providers.common.template_adapter import TemplateProviderAdapter

MANIFEST = build_template_manifest(
    template_id="template_provider_agent_provider",
    name="Template Provider-Native Agent Provider",
    capabilities=ProviderCapabilities(
        agent_module=True,
        tool_use=True,
        file_upload=True,
    ),
    operations=[ProviderOperation.RUN_PROVIDER_AGENT],
    intended_auth_shape="oauth",
    agent_module=ManifestAgentModule(
        supported=True,
        type="provider_agent_template",
        state_model="unknown",
        supports_provider_tools="unknown",
        supports_platform_tools=False,
        provider_managed_state="unknown",
    ),
    security=ManifestSecurity(
        provider_side_tools_allowed_by_default=False,
        requires_capability_firewall=True,
        requires_evaluation=True,
        requires_audit=True,
    ),
    extra_notes=(
        "Provider Agent Capability != Platform Agent Runtime (12 §core rule).",
        "Exists only to preserve architecture support for future provider-native agents (31 §8).",
    ),
)


def build_adapter() -> TemplateProviderAdapter:
    """Return the non-functional adapter for this template (raises on invoke)."""
    return TemplateProviderAdapter(MANIFEST)
