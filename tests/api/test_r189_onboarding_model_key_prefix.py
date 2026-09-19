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
- a payload WITH ``model_key_prefix`` yields ``<prefix>/<provider_model_name>``;
- REPOSITORY FACT (wins over the directive's expectation): a SECOND provider
  onboarded with the same prefix is refused at step 12 (duplicate model key,
  full rollback) — the exposure alone does not bind one model to two
  providers; that is PROPOSAL P-R189-01 (model identity), not R189 work;
- explicit Provider + Model selection through the ONE router is unchanged:
  an ``explicit_model`` policy naming the shared key with ``provider_id``
  narrows to that provider exactly as before;
- the served contract (request model JSON schema) carries the field.

Hermetic: FakeAdapter, in-memory registries, no network.
"""

from __future__ import annotations

import pytest

from apps.api.provider_onboarding import GatewayOnboardRequest
from core.contracts.domain import ProviderStatus
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest
from core.routing.errors import NoEligibleCandidates
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


class TestPrefixAndRoutingOnCurrentTree:
    """Repository fact (R189 disagreement recorded in R189-DEC-02): the walker's
    step 12 registers a NEW Model per key and refuses a duplicate key with full
    rollback (pinned by tests/providers/test_onboarding_service.py). So the
    additive API exposure does NOT by itself bind one model to two onboarded
    providers — that needs a model-identity change (PROPOSAL P-R189-01, not
    implemented). These pins freeze what the tree actually does today."""

    def test_second_provider_with_same_prefix_is_refused_and_rolled_back(self) -> None:
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
        assert second.status_code == 409
        assert "step-12-register-bindings" in second.text
        # Rolled back completely: only the first provider owns shared/cand-1.
        model = world.models.get("shared/cand-1")
        providers = {b.provider_id for b in world.bindings.bindings_for_model(model.id)}
        assert providers == {world.providers.get("gw_alpha").provider.id}
        assert "gw_beta" not in world.providers.all_keys()

    def test_explicit_provider_plus_model_selection_is_unchanged(self) -> None:
        world = RouteWorld()
        assert world.post(_body(model_key_prefix="shared")).status_code == 201
        entry = world.providers.get("gw_alpha")
        # Onboarded providers start DISABLED (walker posture); enable so the
        # ONE router can see it — same registries, no second roster.
        world.providers.replace(
            entry.provider.model_copy(update={"status": ProviderStatus.ACTIVE}), entry.manifest
        )
        router = SimpleScoringRouter(world.providers, world.models, world.bindings)
        # 11 §14 rule 4: explicit provider narrowing is by provider_key (the
        # served ExplicitModelPolicy.provider_id carries the key) — unchanged.
        decision = router.route(
            RoutingRequest(
                operation=ProviderOperation.GENERATE_TEXT,
                model_policy=ExplicitModelPolicy(
                    type="explicit_model", model_id="shared/cand-1", provider_id="gw_alpha"
                ),
            )
        )
        assert decision.selected.provider_id == entry.provider.id
        assert decision.selected.model_id == world.models.get("shared/cand-1").id
        with pytest.raises(NoEligibleCandidates):
            router.route(
                RoutingRequest(
                    operation=ProviderOperation.GENERATE_TEXT,
                    model_policy=ExplicitModelPolicy(
                        type="explicit_model", model_id="shared/cand-1", provider_id="gw_other"
                    ),
                )
            )
