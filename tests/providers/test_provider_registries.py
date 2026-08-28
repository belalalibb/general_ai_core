"""Registry + health aggregation semantics (T-IMPL-019; 30 §4/§5/§7/§11, 31 §10).

Hermetic — pure in-memory registries, no network, no adapters involved.
Every 31 §10 rule is asserted verbatim:

    template_disabled providers are excluded from routing
    is_functional=false providers are excluded from execution
    real_provider_required=true providers cannot pass health checks

Plus: registry trusts ONLY the manifest (30 §4.2), unknown capability =>
DENY (30 §7), provider health != account health (30 §11), duplicate
registration rejected, Model != Provider != Binding kept separate (03 §4).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    AccountHealthCheckState,
    ProviderHealthState,
    ProviderManifest,
    ProviderOperation,
)
from core.providers import (
    BindingNotFound,
    BindingRegistry,
    DuplicateRegistration,
    ModelNotRegistered,
    ModelRegistry,
    ProviderNotEligible,
    ProviderNotRegistered,
    ProviderRegistry,
    RegisteredProvider,
    aggregate_provider_health,
)

# --- fixtures ----------------------------------------------------------------------


def _manifest(**overrides: object) -> ProviderManifest:
    payload: dict[str, object] = {
        "id": "real_text",
        "name": "Real Text Provider",
        "version": "1.0.0",
        "status": "active",
        "auth": {"types": ["api_key"], "supports_refresh": False},
        "account_pool": {"supported": False},
        "capabilities": {"chat": True},
        "operations": ["generate_text"],
        "models": {"discovery": "static", "static_models": ["real-text-1"]},
        "rate_limits": {"strategy": "provider_defined"},
        "health": {"checks": ["ping"]},
        "errors": {"mapping": "error_map.json"},
    }
    payload.update(overrides)
    return ProviderManifest.model_validate(payload)


def _template_manifest() -> ProviderManifest:
    # Exactly the 31 §7 template markers.
    return _manifest(
        id="template_chat_text_provider",
        name="Template Chat/Text Provider",
        status="template_disabled",
        is_template=True,
        is_functional=False,
        real_provider_required=True,
    )


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=False,
    )


def _model(key: str, status: ModelStatus = ModelStatus.ACTIVE) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.FAST,
        modalities=["text"],
        capabilities=["reasoning"],
        status=status,
    )


# --- provider registry: registration -----------------------------------------------


def test_register_and_lookup_by_key_and_id() -> None:
    reg = ProviderRegistry()
    provider = _provider("real_text")
    reg.register(provider, _manifest())
    assert reg.get("real_text").provider is provider
    assert reg.get_by_id(provider.id).provider is provider


def test_duplicate_registration_is_rejected() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("real_text"), _manifest())
    with pytest.raises(DuplicateRegistration):
        reg.register(_provider("real_text"), _manifest())


def test_unknown_provider_raises_not_registered() -> None:
    reg = ProviderRegistry()
    with pytest.raises(ProviderNotRegistered):
        reg.get("nope")


def test_templates_are_loadable_for_scaffolding(state_ok: None = None) -> None:
    # 31 §10: the registry MAY load templates (schema validation/docs/tests).
    reg = ProviderRegistry()
    reg.register(_provider("template_chat"), _template_manifest())
    assert "template_chat" in reg.all_keys()


# --- provider registry: 31 §10 exclusion rules --------------------------------------


def test_template_disabled_providers_are_excluded_from_routing() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("template_chat"), _template_manifest())
    reg.register(_provider("real_text"), _manifest())
    keys = [c.provider.provider_key for c in reg.routing_candidates()]
    assert keys == ["real_text"]


def test_is_functional_false_providers_are_excluded_from_execution() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("broken"), _manifest(id="broken", is_functional=False))
    with pytest.raises(ProviderNotEligible):
        reg.ensure_eligible("broken", ProviderOperation.GENERATE_TEXT)


def test_template_provider_cannot_pass_ensure_eligible() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("template_chat"), _template_manifest())
    with pytest.raises(ProviderNotEligible):
        reg.ensure_eligible("template_chat", ProviderOperation.GENERATE_TEXT)


def test_disabled_domain_status_is_excluded_from_routing_and_execution() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("real_text", ProviderStatus.DISABLED), _manifest())
    assert reg.routing_candidates() == []
    with pytest.raises(ProviderNotEligible):
        reg.ensure_eligible("real_text", ProviderOperation.GENERATE_TEXT)


def test_template_status_word_alone_marks_a_template() -> None:
    # Defense in depth: status="template_disabled" excludes even if the
    # boolean flags were forgotten.
    reg = ProviderRegistry()
    reg.register(_provider("sneaky"), _manifest(id="sneaky", status="template_disabled"))
    assert reg.routing_candidates() == []


# --- provider registry: manifest-driven eligibility (30 §4.2/§5/§7) -----------------


def test_undeclared_operation_makes_provider_ineligible() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("real_text"), _manifest())
    with pytest.raises(ProviderNotEligible):
        reg.ensure_eligible("real_text", ProviderOperation.GENERATE_IMAGE)


def test_declared_operation_passes_ensure_eligible() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("real_text"), _manifest())
    entry = reg.ensure_eligible("real_text", ProviderOperation.GENERATE_TEXT)
    assert entry.manifest.id == "real_text"


def test_routing_candidates_filter_by_declared_operation() -> None:
    reg = ProviderRegistry()
    reg.register(_provider("real_text"), _manifest())
    assert reg.routing_candidates(ProviderOperation.GENERATE_IMAGE) == []
    assert len(reg.routing_candidates(ProviderOperation.GENERATE_TEXT)) == 1


def test_unknown_capability_is_denied() -> None:
    # 30 §7 / 20 §4: unknown capability => DENY, never guessed.
    reg = ProviderRegistry()
    reg.register(_provider("real_text"), _manifest())
    assert reg.supports_capability("real_text", "chat") is True
    assert reg.supports_capability("real_text", "vision_input") is False
    assert reg.supports_capability("real_text", "quantum_teleport") is False


# --- model registry ------------------------------------------------------------------


def test_model_register_lookup_and_unknown_rejection() -> None:
    reg = ModelRegistry()
    model = _model("fast-1")
    reg.register(model)
    assert reg.get("fast-1") is model
    assert reg.get_by_id(model.id) is model
    with pytest.raises(ModelNotRegistered):
        reg.get("nope")
    with pytest.raises(DuplicateRegistration):
        reg.register(model)


def test_only_active_models_enter_the_routing_pool() -> None:
    reg = ModelRegistry()
    reg.register(_model("fast-1"))
    reg.register(_model("old-1", ModelStatus.DEPRECATED))
    reg.register(_model("off-1", ModelStatus.DISABLED))
    assert [m.model_key for m in reg.active_models()] == ["fast-1"]


def test_capability_filter_uses_declared_capabilities_only() -> None:
    reg = ModelRegistry()
    reg.register(_model("fast-1"))
    assert [m.model_key for m in reg.models_with_capability("reasoning")] == ["fast-1"]
    assert reg.models_with_capability("vision") == []


def test_tier_filter_matches_router_tier_policy_semantics() -> None:
    # 41 §9 Tier Registry (T-IMPL-055): tier.value comparison against an OPEN
    # string — the exact TierModelPolicy hard-filter semantics (10 §13.2);
    # ACTIVE models only; unknown tier => empty, never guessed (11 §5).
    reg = ModelRegistry()
    reg.register(_model("fast-1"))
    reg.register(_model("fast-off", ModelStatus.DISABLED))
    assert [m.model_key for m in reg.models_in_tier("fast")] == ["fast-1"]
    assert reg.models_in_tier("max") == []
    assert reg.models_in_tier("admin_custom_tier") == []


def test_modality_filter_uses_declared_modalities_only() -> None:
    # 41 §9 Modality Registry (T-IMPL-055): same declared-only semantics as
    # the Router's model-level exclusion (11 §5) — undeclared => excluded.
    reg = ModelRegistry()
    reg.register(_model("fast-1"))  # modalities=["text"]
    assert [m.model_key for m in reg.models_with_modality("text")] == ["fast-1"]
    assert reg.models_with_modality("image") == []
    assert reg.models_with_modality("not_a_modality") == []


def test_registry_answers_eligibility_without_provider_http() -> None:
    # 41 §9 exit criterion: "Which models are eligible for task X?" answered
    # from declarations alone — this test constructs NO adapter, NO transport,
    # NO provider registration at all; only Model declarations exist.
    reg = ModelRegistry()
    reg.register(_model("fast-1"))
    eligible = [
        m.model_key
        for m in reg.models_with_capability("reasoning")
        if m in reg.models_in_tier("fast") and m in reg.models_with_modality("text")
    ]
    assert eligible == ["fast-1"]


# --- binding registry ----------------------------------------------------------------


def test_binding_register_lookup_and_per_model_per_provider_views() -> None:
    reg = BindingRegistry()
    provider_id, model_id = uuid4(), uuid4()
    binding = ProviderModelBinding(
        provider_id=provider_id,
        model_id=model_id,
        provider_model_name="real-text-1",
        availability=BindingAvailability.AVAILABLE,
    )
    reg.register(binding)
    assert reg.get(provider_id, model_id) is binding
    assert reg.bindings_for_model(model_id) == [binding]
    assert reg.bindings_for_provider(provider_id) == [binding]
    with pytest.raises(DuplicateRegistration):
        reg.register(binding)
    with pytest.raises(BindingNotFound):
        reg.get(uuid4(), model_id)


# --- health aggregation (30 §11, 31 §10) ---------------------------------------------


def _entry(manifest: ProviderManifest | None = None) -> RegisteredProvider:
    reg = ProviderRegistry()
    m = manifest if manifest is not None else _manifest()
    reg.register(_provider(m.id), m)
    return reg.get(m.id)


def test_template_provider_cannot_pass_health_checks() -> None:
    health = aggregate_provider_health(_entry(_template_manifest()))
    assert health.state is ProviderHealthState.UNAVAILABLE


def test_no_accounts_and_no_signal_is_healthy() -> None:
    # Account pools are optional (30 §10.1): no accounts is not evidence.
    health = aggregate_provider_health(_entry())
    assert health.state is ProviderHealthState.HEALTHY


def test_one_failed_account_degrades_but_never_kills_the_provider() -> None:
    # 30 §11: do not confuse "one account failed" with "provider is down".
    health = aggregate_provider_health(
        _entry(),
        {
            "acc-1": AccountHealthCheckState.READY,
            "acc-2": AccountHealthCheckState.AUTH_EXPIRED,
        },
    )
    assert health.state is ProviderHealthState.DEGRADED
    assert health.accounts["acc-1"] is AccountHealthCheckState.READY


def test_even_all_accounts_failing_is_account_scope_evidence_only() -> None:
    health = aggregate_provider_health(
        _entry(),
        {
            "acc-1": AccountHealthCheckState.INVALID,
            "acc-2": AccountHealthCheckState.COOLDOWN,
        },
    )
    assert health.state is ProviderHealthState.DEGRADED
    assert health.state is not ProviderHealthState.UNAVAILABLE


def test_explicit_provider_scope_signal_wins_over_account_arithmetic() -> None:
    health = aggregate_provider_health(
        _entry(),
        {"acc-1": AccountHealthCheckState.READY},
        provider_signal=ProviderHealthState.SUSPENDED,
    )
    assert health.state is ProviderHealthState.SUSPENDED


def test_all_accounts_ready_is_healthy() -> None:
    health = aggregate_provider_health(
        _entry(),
        {"acc-1": AccountHealthCheckState.READY},
    )
    assert health.state is ProviderHealthState.HEALTHY
