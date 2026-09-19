"""R190 — hydration replay with ONE logical Model bound to TWO providers.

RED on the R189 tree: ``hydrate_gateway_providers`` calls
``models.register(model)`` for every binding of every provider, so a Model
row shared by two gateway providers raises ``DuplicateRegistration`` on
restart. GREEN: registration of an already-registered Model id is skipped
(idempotent); real corruption (binding without model row) stays loud.
"""

from __future__ import annotations

from uuid import uuid4

from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    Modality,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from tests.composition.test_provider_onboarding_hydration import (
    FakeCatalog,
    FakeDatabase,
    HydrationWorld,
    _definition,
    _hydrate,
)


def _provider(key: str) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=ProviderStatus.DISABLED,
        auth_types=[AuthType.CUSTOM],
        supports_account_pool=False,
    )


def test_shared_model_hydrates_once_with_two_bindings() -> None:
    a, b = _provider("gw_alpha"), _provider("gw_beta")
    model = Model(
        id=uuid4(),
        model_key="logical/alpha-1",
        display_name="alpha-1",
        tier=ModelTier.MEDIUM,
        modalities=[Modality.TEXT],
        capabilities=[],
        status=ModelStatus.ACTIVE,
    )
    bindings = [
        ProviderModelBinding(
            provider_id=p.id,
            model_id=model.id,
            provider_model_name="alpha-1",
            availability=BindingAvailability.AVAILABLE,
        )
        for p in (a, b)
    ]
    db = FakeDatabase(
        gateway_registrations=FakeCatalog(
            [(a.id, _definition("gw_alpha")), (b.id, _definition("gw_beta"))]
        ),
        provider_catalog=FakeCatalog([a, b]),
        model_catalog=FakeCatalog([model]),
        binding_catalog=FakeCatalog(bindings),
    )
    world = HydrationWorld()
    hydrated = _hydrate(world, db, settings=None)
    assert sorted(hydrated) == ["gw_alpha", "gw_beta"]
    assert [m.model_key for m in world.models.all_models()] == ["logical/alpha-1"]
    assert {x.provider_id for x in world.bindings.bindings_for_model(model.id)} == {a.id, b.id}
