"""R189 — P-R188-01 (operator YES): additive ``model_key_prefix`` on the
EXISTING onboarding request (10 §… none: admin surface; 31 onboarding).

Facts pinned BEFORE the change (RED): ``GatewayOnboardRequest`` is
``extra="forbid"`` and has no ``model_key_prefix`` field, so a payload
carrying it is refused with the closed-shape 422 — while the service
(``ProviderOnboardingService.onboard``) already accepts the parameter.

After the change (GREEN) the SAME test module proves additivity:
- an OLD payload (no new field) still yields the identical stored model key
  ``<provider_key>/<provider_model_name>`` and the identical persisted
  definition semantics (the field is simply absent / None);
- a payload WITH ``model_key_prefix`` yields ``<prefix>/<provider_model_name>``
  — the SAME key for two providers sharing the prefix (same model, different
  provider), which is the whole point of P-R188-01;
- explicit Provider + Model selection through the ONE router is unchanged:
  an ``explicit_model`` policy naming the shared key with ``provider_id``
  narrows to that provider exactly as before;
- the served contract (request model JSON schema) carries the field.

Hermetic: FakeAdapter, in-memory registries, no network.
"""

from __future__ import annotations

from uuid import UUID

from apps.api.provider_onboarding import GatewayOnboardRequest
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.routing.router import SimpleScoringRouter
from tests.api.test_provider_onboarding_api import RouteWorld, _body
from tests.providers.test_onboarding_service import FakeAdapter, _manifest


class TestAdditiveField:
    def test_served_request_contract_declares_model_key_prefix(self) -> None:
        schema = GatewayOnboardRequest.model_json_schema()
        assert "model_key_prefix" in schema["properties"], "field must be in the served contract"
        assert "model_key_prefix" not in schema.get("required", [])

    def test_old_payload_without_field_yields_identical_stored_model_key(self) -> None:
        world = RouteWorld()
        response = world.post(_body())  # the pre-R189 payload, byte-for-byte
        assert response.status_code == 201, response.text
        assert world.models.get("gw_alpha/cand-1").model_key == "gw_alpha/cand-1"
        assert tuple(response.json()["registered_model_keys"]) == ("gw_alpha/cand-1",)
        # Persisted definition: the field is not invented into old payloads.
        ((_, definition),) = world.persisted
        assert definition.get("model_key_prefix") is None

    def test_payload_with_prefix_registers_prefixed_key(self) -> None:
        world = RouteWorld()
        response = world.post(_body(model_key_prefix="shared"))
        assert response.status_code == 201, response.text
        assert tuple(response.json()["registered_model_keys"]) == ("shared/cand-1",)
        assert world.models.get("shared/cand-1").model_key == "shared/cand-1"
        ((_, definition),) = world.persisted
        assert definition["model_key_prefix"] == "shared"


class TestSameModelDifferentProvider:
    def _two_providers(self) -> RouteWorld:
        world = RouteWorld()
        first = world.post(_body(model_key_prefix="shared"))
        assert first.status_code == 201, first.text
        world.adapter = FakeAdapter(manifest=_manifest(id="gw_beta", name="Gateway Beta"))
        second = world.post(
            _body(
                provider_key="gw_beta",
                display_name="Gateway Beta",
                credential_ref="credref_beta",
                route_token_ref="credref_route_beta",
                model_key_prefix="shared",
            )
        )
        assert second.status_code == 201, second.text
        return world

    def test_shared_prefix_binds_one_model_to_two_providers(self) -> None:
        world = self._two_providers()
        model = world.models.get("shared/cand-1")
        providers = {b.provider_id for b in world.bindings.bindings_for_model(model.id)}
        assert providers == {
            world.providers.get("gw_alpha").provider.id,
            world.providers.get("gw_beta").provider.id,
        }

    def test_explicit_provider_plus_model_selection_is_unchanged(self) -> None:
        world = self._two_providers()
        # Onboarded providers start DISABLED (walker posture); enable both so
        # routing can see them — the SAME registries, the ONE router.
        for key in ("gw_alpha", "gw_beta"):
            entry = world.providers.get(key)
            world.providers.replace(
                entry.provider.model_copy(update={"status": "active"}), entry.manifest
            )
        router = SimpleScoringRouter(world.providers, world.models, world.bindings)
        beta = world.providers.get("gw_beta").provider
        decision = router.route(
            RoutingRequest(
                operation=ProviderOperation.GENERATE_TEXT,
                model_policy=ExplicitModelPolicy(
                    type="explicit_model", model_id="shared/cand-1", provider_id=str(beta.id)
                ),
            )
        )
        assert decision.selected.provider_id == beta.id
        assert decision.selected.model_id == world.models.get("shared/cand-1").id
        assert isinstance(UUID(str(decision.selected.provider_id)), UUID)
