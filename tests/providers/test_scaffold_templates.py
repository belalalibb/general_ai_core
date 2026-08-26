"""Scaffold-state test suite (T-IMPL-020; 31 §7, §10, §11, §12).

Verifies EXACTLY what 31 §11 requires for scaffold-only state — and nothing
that would pretend generation works:

    manifest schema validation
    templates are disabled
    templates are excluded from routing
    templates cannot execute generation
    template health check returns non-functional
    diverse capability categories are represented
    provider contract can be implemented later
    Core does not import provider internals

Hermetic: no network, no credentials, no secret material (20 §5, 41 §49).
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from core.contracts.domain import AuthType, CredentialStatus, Provider, ProviderStatus
from core.contracts.provider import (
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderHealthState,
    ProviderManifest,
    ProviderOperation,
)
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import (
    ProviderRegistry,
    RegisteredProvider,
    aggregate_provider_health,
)
from providers.common.manifest_builder import TEMPLATE_NOTES, build_template_manifest
from providers.common.template_adapter import (
    TemplateProviderAdapter,
    TemplateProviderInvoked,
)
from providers.templates import TEMPLATE_MODULES, all_template_manifests

# --- fixtures ----------------------------------------------------------------------

EXPECTED_TEMPLATE_IDS = (
    "template_chat_text_provider",
    "template_reasoning_provider",
    "template_coding_provider",
    "template_vision_provider",
    "template_image_generation_provider",
    "template_audio_stt_provider",
    "template_audio_tts_provider",
    "template_embeddings_provider",
    "template_rerank_provider",
    "template_moderation_safety_provider",
    "template_multimodal_provider",
    "template_provider_agent_provider",
)


def _domain_provider_for(manifest: ProviderManifest) -> Provider:
    """Domain registry entry for a template (loading is legal per 31 §10).

    Templates hold no credentials; the domain ``auth_types`` list cannot be
    empty (03 §4), so the scaffold registers them as ``custom`` + DISABLED —
    the exclusion tests below prove none of this makes them eligible.
    """
    return Provider(
        id=uuid4(),
        provider_key=manifest.id,
        display_name=manifest.name,
        status=ProviderStatus.DISABLED,
        auth_types=[AuthType.CUSTOM],
        supports_account_pool=manifest.account_pool.supported,
    )


def _registry_with_all_templates() -> ProviderRegistry:
    reg = ProviderRegistry()
    for manifest in all_template_manifests():
        reg.register(_domain_provider_for(manifest), manifest)
    return reg


# --- 31 §11: manifest schema validation ---------------------------------------------


def test_all_twelve_templates_load_and_validate_against_the_contract_schema() -> None:
    manifests = all_template_manifests()
    assert len(manifests) == 12
    for manifest in manifests:
        # Round-trip through the schema: what loaded also re-validates.
        assert ProviderManifest.model_validate(manifest.model_dump()) == manifest


def test_template_ids_cover_all_twelve_diversity_categories_in_order() -> None:
    # 31 §6: the 12 categories, in canonical order.
    assert tuple(m.id for m in all_template_manifests()) == EXPECTED_TEMPLATE_IDS


def test_every_template_module_exposes_manifest_and_adapter_builder() -> None:
    for module in TEMPLATE_MODULES:
        assert isinstance(module.MANIFEST, ProviderManifest)
        adapter = module.build_adapter()
        assert isinstance(adapter, TemplateProviderAdapter)
        assert adapter.get_manifest() == module.MANIFEST


# --- 31 §11: templates are disabled (the §7 marker set, verbatim) -------------------


def test_every_template_carries_the_full_31s7_marker_set() -> None:
    for manifest in all_template_manifests():
        assert manifest.status == "template_disabled"
        assert manifest.is_template is True
        assert manifest.is_functional is False
        assert manifest.real_provider_required is True
        assert manifest.auth.types == []  # verbatim: templates hold no credentials
        assert manifest.models.discovery == "not_implemented"
        # 31 §7 verbatim scaffold notes, first.
        assert tuple(manifest.notes[: len(TEMPLATE_NOTES)]) == TEMPLATE_NOTES


def test_templates_carry_no_secret_material_anywhere() -> None:
    # 20 §5: scan the full serialized manifest for secret-looking keys.
    forbidden_fragments = ("secret", "token", "password", "cookie_value")
    for manifest in all_template_manifests():
        dumped = manifest.model_dump_json().lower()
        for fragment in forbidden_fragments:
            assert fragment not in dumped, (manifest.id, fragment)


# --- 31 §11: templates are excluded from routing -------------------------------------


def test_templates_are_loadable_but_never_routing_candidates() -> None:
    reg = _registry_with_all_templates()
    # Loading is legal (31 §10): all 12 are visible.
    assert len(reg.all_keys()) == 12
    # Routing exclusion is total — for every operation and unfiltered.
    assert reg.routing_candidates() == []
    for operation in ProviderOperation:
        assert reg.routing_candidates(operation) == []


def test_templates_are_excluded_from_execution_eligibility() -> None:
    reg = _registry_with_all_templates()
    for manifest in all_template_manifests():
        declared = manifest.operations[0]
        with pytest.raises(Exception) as excinfo:
            reg.ensure_eligible(manifest.id, declared)
        assert "template" in str(excinfo.value)


# --- 31 §11: templates cannot execute generation -------------------------------------


def test_template_generate_always_raises_for_every_declared_operation() -> None:
    for module in TEMPLATE_MODULES:
        adapter = module.build_adapter()
        for operation in module.MANIFEST.operations:
            request = ProviderGenerateRequest(
                request_id=uuid4(),
                tenant_id=uuid4(),
                operation=operation,
                provider_model_name="any-model",
                credential_ref="vault://tenants/x/creds/y",
                payload={"input": "scaffold"},
            )
            with pytest.raises(TemplateProviderInvoked):
                asyncio.run(adapter.generate(request))


def test_template_discovery_raises_and_credential_check_reports_invalid() -> None:
    adapter = TEMPLATE_MODULES[0].build_adapter()
    with pytest.raises(TemplateProviderInvoked):
        asyncio.run(adapter.discover_models())
    health = asyncio.run(adapter.validate_credential("vault://tenants/x/creds/y"))
    assert health.status is CredentialStatus.INVALID
    assert health.credential_ref == "vault://tenants/x/creds/y"  # opaque, unresolved


def test_template_invocation_normalizes_to_unsupported_capability() -> None:
    adapter = TEMPLATE_MODULES[0].build_adapter()
    error = adapter.normalize_error(
        TemplateProviderInvoked("template_chat_text_provider", "generate_text")
    )
    assert error.category is ProviderErrorCategory.UNSUPPORTED_CAPABILITY
    assert error.retryable is False


# --- 31 §11: template health check returns non-functional ----------------------------


def test_template_health_check_is_unavailable_for_both_scopes() -> None:
    for module in TEMPLATE_MODULES:
        adapter = module.build_adapter()
        for scope in ("provider", "account"):
            health = asyncio.run(adapter.health_check(scope))
            assert health.state is ProviderHealthState.UNAVAILABLE


def test_template_health_aggregation_is_unavailable_regardless_of_signals() -> None:
    # 31 §10: real_provider_required=true providers cannot pass health checks —
    # even a (bogus) healthy provider-scope signal cannot lift a template.
    manifest = all_template_manifests()[0]
    entry = RegisteredProvider(_domain_provider_for(manifest), manifest)
    health = aggregate_provider_health(
        entry,
        provider_signal=ProviderHealthState.HEALTHY,
    )
    assert health.state is ProviderHealthState.UNAVAILABLE


# --- 31 §11: diverse capability categories are represented ---------------------------


def test_capability_diversity_spans_the_required_shapes() -> None:
    manifests = {m.id: m for m in all_template_manifests()}
    caps = {mid: m.capabilities for mid, m in manifests.items()}
    # text-only / image-only / embeddings-only / moderation-only shapes exist.
    assert caps["template_chat_text_provider"].chat is True
    assert caps["template_image_generation_provider"].image_generation is True
    assert caps["template_image_generation_provider"].chat is False
    assert caps["template_embeddings_provider"].embeddings is True
    assert caps["template_embeddings_provider"].chat is False
    assert caps["template_rerank_provider"].rerank is True
    assert caps["template_moderation_safety_provider"].moderation is True
    # multimodal shape declares several modalities.
    multi = caps["template_multimodal_provider"]
    assert multi.chat and multi.vision_input and multi.image_generation
    # provider-native agent shape (31 §8).
    agent = manifests["template_provider_agent_provider"]
    assert agent.capabilities.agent_module is True
    assert agent.capabilities.tool_use is True


def test_auth_shape_diversity_is_recorded_without_functional_auth() -> None:
    # 31 §12: api_key / oauth / session_cookie / no-auth-local all represented —
    # as INTENT notes only; functional auth stays empty on every template.
    notes_by_id = {m.id: " ".join(m.notes) for m in all_template_manifests()}
    assert "api_key" in notes_by_id["template_chat_text_provider"]
    assert "oauth" in notes_by_id["template_reasoning_provider"]
    assert "session_cookie" in notes_by_id["template_multimodal_provider"]
    assert "no-auth local" in notes_by_id["template_embeddings_provider"]
    assert "no-auth local" in notes_by_id["template_moderation_safety_provider"]


def test_account_pool_shape_is_diverse_not_forced() -> None:
    # 31 §12: the scaffold must not force one lifecycle — exactly the
    # session/cookie multimodal template declares an account pool.
    pool_ids = {m.id for m in all_template_manifests() if m.account_pool.supported}
    assert pool_ids == {"template_multimodal_provider"}


def test_provider_agent_template_preserves_the_31s8_security_posture() -> None:
    agent = all_template_manifests()[-1]
    assert agent.id == "template_provider_agent_provider"
    assert agent.agent_module is not None
    assert agent.agent_module.supported is True
    assert agent.agent_module.supports_platform_tools is False
    assert agent.agent_module.state_model == "unknown"  # unknown never = supported
    assert agent.security is not None
    assert agent.security.provider_side_tools_allowed_by_default is False
    assert agent.security.requires_capability_firewall is True
    assert agent.security.requires_evaluation is True
    assert agent.security.requires_audit is True


# --- 31 §11: provider contract can be implemented later ------------------------------


def test_template_adapter_satisfies_the_provider_adapter_port() -> None:
    # Structural check: the scaffold proves the 30 §8 contract SHAPE is
    # implementable later (31 §11). Static: the annotation below is checked
    # by mypy --strict. Dynamic: every port method must be present + callable.
    adapter: ProviderAdapterPort = TEMPLATE_MODULES[0].build_adapter()
    for method in (
        "get_manifest",
        "validate_credential",
        "discover_models",
        "get_capabilities",
        "generate",
        "health_check",
        "normalize_error",
    ):
        assert callable(getattr(adapter, method))


def test_template_adapter_rejects_non_template_manifests() -> None:
    # Guard: the non-functional base can never wrap a real provider manifest.
    real = all_template_manifests()[0].model_copy(
        update={"is_template": False, "is_functional": True, "status": "active"}
    )
    with pytest.raises(ValueError):
        TemplateProviderAdapter(real)


# --- 31 §11: Core does not import provider internals ---------------------------------


def test_core_does_not_import_provider_internals() -> None:
    # Belt-and-braces beside the import-linter contract: importing every
    # core.providers module must not pull in the providers package.
    import importlib
    import sys

    for name in ("core.providers.ports", "core.providers.registry"):
        module = importlib.import_module(name)
        source = (module.__file__ or "").replace("\\", "/")
        assert "/core/" in source
    core_loaded = [m for m in sys.modules if m.startswith("core.")]
    for module_name in core_loaded:
        loaded = sys.modules[module_name]
        for attr_value in vars(loaded).values():
            attr_module = getattr(attr_value, "__module__", "")
            assert not str(attr_module).startswith("providers."), (
                module_name,
                attr_module,
            )


# --- 31 §9: pending ledger exists and claims nothing ---------------------------------


def test_pending_real_providers_ledger_records_scaffold_state() -> None:
    from pathlib import Path

    ledger = Path(__file__).resolve().parents[2] / "providers" / "_pending_real_providers.md"
    assert ledger.is_file()
    text = ledger.read_text(encoding="utf-8")
    assert "No real AI providers are implemented yet." in text
    assert "NOT-CLAIMED" in text  # 41 §49 explicit not-claimed record


def test_manifest_builder_refuses_nothing_but_keeps_markers_fixed() -> None:
    # Any manifest built through the shared builder carries the marker set —
    # a template author cannot accidentally produce an activatable manifest.
    from core.contracts.provider import ProviderCapabilities

    built = build_template_manifest(
        template_id="template_future_thing",
        name="Future Thing",
        capabilities=ProviderCapabilities(chat=True),
        operations=[ProviderOperation.GENERATE_TEXT],
        intended_auth_shape="api_key",
    )
    assert built.status == "template_disabled"
    assert built.is_template and not built.is_functional
    assert built.real_provider_required is True
    assert built.auth.types == []
