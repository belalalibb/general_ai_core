"""R190 — P-R189-01 (operator YES): ONE logical Model + MANY provider bindings.

RED on the R189 tree: onboarding a SECOND provider with the same explicit
``model_key_prefix`` is refused at step 12 (duplicate model key, full
rollback) — see R189-DEC-02 §4 (repository disagreement recorded).

GREEN (after the step-12 change in ``core/providers/onboarding.py``) proves
the directive's A–J list on the SAME registries, the ONE router and the ONE
execution service — no aliases, no second registry, no routing branch:

A. one logical Model after onboarding both providers;
B. two ProviderModelBindings point to that same Model;
C. no duplicate logical Model is created;
D. first-provider state remains intact;
E. a failed second onboarding does not corrupt existing state;
F. Model-only routing sees both eligible providers;
G. explicit Provider + Model still works;
H. same-model fallback still works (R188 walk);
I. a cooling provider remains excluded even though it shares the Model;
J. the old onboarding payload shape (no prefix) is behaviorally unchanged.

Hermetic: FakeAdapter / ScriptedAdapter, in-memory registries, no network.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from core.contracts.domain import AuthType, ProviderStatus
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.provider import ProviderErrorCategory, ProviderOperation
from core.contracts.routing import RoutingRequest
from core.execution import ExecutionService
from core.providers import OnboardingRefused
from core.providers.errors import ProviderNotRegistered
from core.routing.capacity import ResourceSignalBoard
from core.routing.errors import NoEligibleCandidates
from core.routing.router import SimpleScoringRouter
from tests.providers.test_onboarding_service import FakeAdapter, World, _manifest, run
from tests.routing.test_r188_capacity_signals import (
    T0,
    ScriptedAdapter,
    _err,
    _no_sleep,
    _run,
)

SHARED = "logical"
KEY = f"{SHARED}/cand-1"


def _onboard(world: World, key: str, *, prefix: str | None, adapter: FakeAdapter | None = None):
    return run(
        world.service.onboard(
            adapter=adapter if adapter is not None else FakeAdapter(manifest=_manifest(id=key)),
            provider_key=key,
            display_name=key,
            auth_types=[AuthType.API_KEY],
            credential_ref=f"secret-ref://{key}",
            model_key_prefix=prefix,
        )
    )


def _two_providers(world: World) -> tuple[UUID, UUID]:
    a = _onboard(world, "prov_a", prefix=SHARED)
    b = _onboard(world, "prov_b", prefix=SHARED)
    return a.provider_id, b.provider_id


def _activate(world: World, key: str) -> None:
    entry = world.providers.get(key)
    world.providers.replace(
        entry.provider.model_copy(update={"status": ProviderStatus.ACTIVE}), entry.manifest
    )


class TestOneLogicalModelManyBindings:
    def test_a_b_c_second_provider_binds_to_the_existing_model(self) -> None:
        world = World()
        pid_a, pid_b = _two_providers(world)
        model = world.models.get(KEY)
        # A + C: exactly one logical Model carries the key (registry is keyed).
        assert [m.model_key for m in world.models.all_models()] == [KEY]
        # B: two bindings, one Model.
        bound = {b.provider_id: b for b in world.bindings.bindings_for_model(model.id)}
        assert set(bound) == {pid_a, pid_b}
        assert all(b.model_id == model.id for b in bound.values())
        # Provider-specific facts stay on the binding side.
        assert bound[pid_b].provider_model_name == "cand-1"

    def test_d_first_provider_state_is_intact_after_second_onboarding(self) -> None:
        world = World()
        first = _onboard(world, "prov_a", prefix=SHARED)
        model_before = world.models.get(KEY)
        binding_before = world.bindings.get(first.provider_id, model_before.id)
        second = _onboard(world, "prov_b", prefix=SHARED)
        assert second.registered_model_keys == (KEY,)
        assert "step-12-register-bindings" in second.steps_passed
        # Same Model object identity (id) — not re-created, not replaced.
        assert world.models.get(KEY).id == model_before.id
        assert world.bindings.get(first.provider_id, model_before.id) == binding_before
        assert world.providers.get("prov_a").provider.id == first.provider_id

    def test_e_failed_second_onboarding_leaves_existing_state_intact(self) -> None:
        world = World()
        first = _onboard(world, "prov_a", prefix=SHARED)
        model = world.models.get(KEY)
        # Second provider: one model reuses the logical key, a second one
        # declares a DIFFERENT modality set for the same logical key of a
        # third model → refused loudly at step 12 (no provider state copied
        # into the Model), and everything THIS onboarding created is undone.
        adapter = FakeAdapter(
            manifest=_manifest(id="prov_b"),
            models=[
                {"provider_model_name": "cand-1", "modalities": ["text"]},
                {"provider_model_name": "cand-new", "modalities": ["text"]},
                {"provider_model_name": "cand-mismatch", "modalities": ["text"]},
            ],
        )
        # Pre-existing logical model with a different modality set.
        _onboard(
            world,
            "prov_c",
            prefix=SHARED,
            adapter=FakeAdapter(
                manifest=_manifest(id="prov_c"),
                models=[{"provider_model_name": "cand-mismatch", "modalities": ["image"]}],
            ),
        )
        with pytest.raises(OnboardingRefused) as exc:
            _onboard(world, "prov_b", prefix=SHARED, adapter=adapter)
        assert exc.value.step == "step-12-register-bindings"
        # Rolled back: prov_b gone, its new model gone, the shared Model and
        # prov_a's binding untouched, prov_c's model untouched.
        with pytest.raises(ProviderNotRegistered):
            world.providers.get("prov_b")
        assert sorted(m.model_key for m in world.models.all_models()) == sorted(
            [KEY, f"{SHARED}/cand-mismatch"]
        )
        assert {b.provider_id for b in world.bindings.bindings_for_model(model.id)} == {
            first.provider_id
        }
        assert world.models.get(KEY).id == model.id

    def test_j_old_payload_shape_without_prefix_is_unchanged(self) -> None:
        world = World()
        report = world.onboard(FakeAdapter(manifest=_manifest(id="cand")), key="cand")
        assert report.registered_model_keys == ("cand/cand-1",)
        # A second provider WITHOUT an explicit prefix never reuses — its
        # default prefix is its own key, so it gets its own logical Model.
        other = world.onboard(FakeAdapter(manifest=_manifest(id="other")), key="other")
        assert other.registered_model_keys == ("other/cand-1",)
        assert len(world.models.all_models()) == 2
        # And a default-prefix collision with foreign state is STILL refused
        # (pre-R190 behavior kept): pre-seed "third/cand-1" under another owner.
        _onboard(world, "seed", prefix="third")
        with pytest.raises(OnboardingRefused) as exc:
            world.onboard(FakeAdapter(manifest=_manifest(id="third")), key="third")
        assert exc.value.step == "step-12-register-bindings"
        with pytest.raises(ProviderNotRegistered):
            world.providers.get("third")


class TestRoutingOverTheSharedModel:
    def _routed_world(self) -> tuple[World, ResourceSignalBoard, SimpleScoringRouter, dict]:
        world = World()
        _two_providers(world)
        _activate(world, "prov_a")
        _activate(world, "prov_b")
        clock = {"now": T0}
        board = ResourceSignalBoard(clock=lambda: clock["now"])
        router = SimpleScoringRouter(world.providers, world.models, world.bindings, signals=board)
        return world, board, router, clock

    @staticmethod
    def _model_only(model_key: str = KEY) -> RoutingRequest:
        return RoutingRequest(
            operation=ProviderOperation.GENERATE_TEXT,
            model_policy=ExplicitModelPolicy(type="explicit_model", model_id=model_key),
        )

    def test_f_model_only_routing_sees_both_providers(self) -> None:
        world, _, router, _ = self._routed_world()
        decision = router.route(self._model_only())
        seen = {
            decision.selected.provider_id,
            *(c.provider_id for c in decision.fallback_candidates),
        }
        assert seen == {
            world.providers.get("prov_a").provider.id,
            world.providers.get("prov_b").provider.id,
        }
        model = world.models.get(KEY)
        assert decision.selected.model_id == model.id
        assert all(c.model_id == model.id for c in decision.fallback_candidates)

    def test_g_explicit_provider_plus_model_still_narrows(self) -> None:
        world, _, router, _ = self._routed_world()
        for key in ("prov_a", "prov_b"):
            decision = router.route(
                RoutingRequest(
                    operation=ProviderOperation.GENERATE_TEXT,
                    model_policy=ExplicitModelPolicy(
                        type="explicit_model", model_id=KEY, provider_id=key
                    ),
                )
            )
            assert decision.selected.provider_id == world.providers.get(key).provider.id
        with pytest.raises(NoEligibleCandidates):
            router.route(
                RoutingRequest(
                    operation=ProviderOperation.GENERATE_TEXT,
                    model_policy=ExplicitModelPolicy(
                        type="explicit_model", model_id=KEY, provider_id="prov_missing"
                    ),
                )
            )

    def test_h_i_same_model_fallback_and_cooling_exclusion(self) -> None:
        world, board, router, clock = self._routed_world()
        by_key = {k: world.providers.get(k).provider.id for k in ("prov_a", "prov_b")}
        adapters = {pid: ScriptedAdapter() for pid in by_key.values()}
        service = ExecutionService(
            adapters=adapters,  # type: ignore[arg-type]
            credential_refs={pid: f"ref-{k}" for k, pid in by_key.items()},
            bindings=world.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
            clock=lambda: clock["now"],
            signals=board,
        )
        first = router.route(self._model_only())
        selected = first.selected.provider_id
        other = next(pid for pid in by_key.values() if pid != selected)
        adapters[selected].script = [
            _err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=30_000)
        ]
        report = _run(
            service.execute_single(
                tenant_id=uuid4(),
                user_id=uuid4(),
                decision=first,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"ask": "hi"},
                request_hash="h",
            )
        )
        # H: same Model, different provider, execution continued.
        model = world.models.get(KEY)
        assert report.execution.status.value == "succeeded"
        attempts = report.nodes[0].attempts
        assert [a.candidate.provider_id for a in attempts] == [selected, other]
        assert all(a.candidate.model_id == model.id for a in attempts)
        # I: the cooling provider is excluded on the next model-only decision.
        second = router.route(self._model_only())
        assert second.selected.provider_id == other
        assert second.fallback_candidates == []
        cooled_key = world.providers.get_by_id(selected).provider.provider_key
        assert any(r.provider_key == cooled_key and "cooldown" in r.reason for r in second.excluded)
        clock["now"] = T0 + timedelta(seconds=31)
        third = router.route(self._model_only())
        assert {
            third.selected.provider_id,
            *(c.provider_id for c in third.fallback_candidates),
        } == set(by_key.values())
