"""R188 slice A — RED first: runtime resource signals close the routing feedback loop.

Authority: R188-DEC-01 (60_DECISION_LOG.md) items A1-A4. Findings on the CURRENT
tree (recorded before this file existed):

* ``SimpleScoringRouter`` routes over STATIC binding availability only; its own
  docstring lists the "rate-limit budget" filter as not implemented.
* ``ExecutionService`` records rate_limited / provider_unavailable outcomes in
  ``AttemptRecord`` but never feeds them anywhere — the next request re-sends work
  to the known-exhausted candidate.

Target behaviour proven here (all hermetic; scripted adapters; injected clock):

1. Model-only request -> dynamic provider resolution (two providers, same model,
   no provider named).
2. Selected provider answers ``rate_limited`` with Retry-After -> the SAME model
   continues on a DIFFERENT eligible provider inside the SAME execution (existing
   failover) AND the next routing decision EXCLUDES the cooling provider with an
   explainable record (new feedback loop) — no work is sent into a known-exhausted
   resource until its cooldown ends.
3. Declared RPM (``ProviderModelBinding.limits_metadata["rpm"]``) is a real
   eligibility constraint: the (provider, model) pair drops out for the rest of the
   window once its declared budget is consumed; another provider serving the model
   absorbs the traffic (distribution).
4. When EVERY candidate is cooling down, ``NoEligibleCandidates`` carries the
   earliest ``retry_after_ms`` so a caller can WAIT rather than fail blindly or
   busy-loop.
5. Explicit provider + model still works and still fails clearly when that provider
   is cooling (explicit choice never outranks availability — 11 §13).
6. Provider internals never cross the boundary: the board holds only normalized
   categories, timestamps and counts — no provider payloads, keys, or accounts.
7. Scale: eligibility lookups are O(1) per candidate; 2 000 (provider, model) pairs
   route in bounded time (recorded, not claimed as "10 000 providers").
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.contracts.domain import (
    AuthType,
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.model_policy import AutoModelPolicy, ExplicitModelPolicy
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
    ProviderOperation,
)
from core.contracts.routing import RoutingRequest
from core.execution import ExecutionService
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.routing.capacity import ResourceSignalBoard  # RED: module does not exist yet
from core.routing.errors import NoEligibleCandidates
from core.routing.router import SimpleScoringRouter

T0 = datetime(2026, 9, 16, 12, 0, 0, tzinfo=UTC)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


def _err(
    category: ProviderErrorCategory, *, retryable: bool = False, retry_after_ms: int | None = None
) -> ProviderError:
    return ProviderError(
        category=category,
        retryable=retryable,
        retry_after_ms=retry_after_ms,
        safe_message=f"fake {category}",
    )


class ScriptedAdapter:
    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(credential_ref=credential_ref, status=CredentialStatus.ACTIVE)

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        return []  # pragma: no cover - unused

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"ok": True}
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id, succeeded=False, error=step, latency_ms=3
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=2,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return _err(ProviderErrorCategory.NON_RETRYABLE_ERROR)


def _manifest(key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": key,
            "name": key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined", "dimensions": ["rpm"]},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.5,
        reliability_score=0.5,
        cost_score=0.5,
        speed_score=0.5,
        status=ModelStatus.ACTIVE,
    )


class World:
    """N pool-less providers all serving the SAME model; one shared signal board."""

    def __init__(self, provider_keys: list[str], *, rpm: dict[str, int] | None = None) -> None:
        self.now = T0
        self.board = ResourceSignalBoard(clock=lambda: self.now)
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.adapters: dict[UUID, ScriptedAdapter] = {}
        self.by_key: dict[str, Provider] = {}
        self.model = _model("shared-model")
        self.models.register(self.model)
        for key in provider_keys:
            provider = Provider(
                id=uuid4(),
                provider_key=key,
                display_name=key,
                status=ProviderStatus.ACTIVE,
                auth_types=[AuthType.API_KEY],
                supports_account_pool=False,
            )
            self.providers.register(provider, _manifest(key))
            limits = {"rpm": rpm[key]} if rpm and key in rpm else {}
            self.bindings.register(
                ProviderModelBinding(
                    provider_id=provider.id,
                    model_id=self.model.id,
                    provider_model_name="shared",
                    availability=BindingAvailability.AVAILABLE,
                    limits_metadata=limits,
                )
            )
            self.adapters[provider.id] = ScriptedAdapter()
            self.by_key[key] = provider
        self.router = SimpleScoringRouter(
            self.providers, self.models, self.bindings, signals=self.board
        )
        self.service = ExecutionService(
            adapters=self.adapters,
            credential_refs={p.id: f"ref-{k}" for k, p in self.by_key.items()},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
            clock=lambda: self.now,
            signals=self.board,
        )

    def key_of(self, provider_id: UUID) -> str:
        return self.providers.get_by_id(provider_id).provider.provider_key

    def route(self, policy: object | None = None) -> Any:
        return self.router.route(
            RoutingRequest(operation=ProviderOperation.GENERATE_TEXT, model_policy=policy)
        )

    def execute(self, decision: Any) -> Any:
        return _run(
            self.service.execute_single(
                tenant_id=uuid4(),
                user_id=uuid4(),
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"ask": "hi"},
                request_hash="h",
            )
        )


# ------------------------------------------------------------------ 1. model-only ---


def test_model_only_request_resolves_a_provider_dynamically() -> None:
    w = World(["alpha", "beta"])
    decision = w.route()  # no policy, no provider, no model named
    assert decision.selected.model_id == w.model.id
    assert w.key_of(decision.selected.provider_id) in {"alpha", "beta"}
    # same model, the OTHER provider is the default fallback route
    assert [c.model_id for c in decision.fallback_candidates] == [w.model.id]
    assert decision.fallback_policy.value == "same_model_different_provider"


# ------------------------------------------- 2. rate limit -> same model elsewhere ---


def test_rate_limited_provider_fails_over_same_model_and_is_excluded_next_time() -> None:
    w = World(["alpha", "beta"])
    first = w.route()
    selected_key = w.key_of(first.selected.provider_id)
    other_key = "beta" if selected_key == "alpha" else "alpha"
    w.adapters[first.selected.provider_id].script = [
        _err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=30_000)
    ]

    report = w.execute(first)

    # existing failover: same model, different provider, execution continues
    assert report.execution.status.value == "succeeded"
    attempts = report.nodes[0].attempts
    assert [w.key_of(a.candidate.provider_id) for a in attempts] == [selected_key, other_key]
    assert all(a.candidate.model_id == w.model.id for a in attempts)

    # NEW feedback loop: the next decision does not send work into the cooling provider
    second = w.route()
    assert w.key_of(second.selected.provider_id) == other_key
    assert second.fallback_candidates == []
    excluded = [r for r in second.excluded if r.provider_key == selected_key]
    assert excluded and "cooldown" in excluded[0].reason
    # ...and after the cooldown the provider is eligible again (no permanent ban)
    w.now = T0 + timedelta(seconds=31)
    third = w.route()
    assert {w.key_of(c.provider_id) for c in [third.selected, *third.fallback_candidates]} == {
        "alpha",
        "beta",
    }


# ---------------------------------------------------------- 3. declared RPM budget ---


def test_declared_rpm_is_a_real_eligibility_constraint_and_traffic_distributes() -> None:
    w = World(["alpha", "beta"], rpm={"alpha": 2, "beta": 100})
    used: list[str] = []
    for _ in range(5):
        decision = w.route()
        report = w.execute(decision)
        assert report.execution.status.value == "succeeded"
        used.append(w.key_of(report.nodes[0].attempts[-1].candidate.provider_id))
    # alpha served at most its declared 2 requests inside the minute; beta absorbed the rest
    assert used.count("alpha") <= 2
    assert used.count("beta") >= 3
    late = w.route()
    reasons = [r.reason for r in late.excluded if r.provider_key == "alpha"]
    assert reasons and "rpm" in reasons[0]
    # a new minute resets the window
    w.now = T0 + timedelta(seconds=61)
    fresh = w.route()
    assert not [r for r in fresh.excluded if r.provider_key == "alpha"]


# -------------------------------------------------- 4. everyone cooling -> wait data ---


def test_all_candidates_cooling_reports_earliest_retry_after_instead_of_blind_failure() -> None:
    w = World(["alpha", "beta"])
    for key, ms in (("alpha", 20_000), ("beta", 5_000)):
        w.board.record_error(
            provider_id=w.by_key[key].id,
            model_id=w.model.id,
            error=_err(ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=ms),
        )
    with pytest.raises(NoEligibleCandidates) as info:
        w.route()
    assert info.value.retry_after_ms == 5_000
    assert len([r for r in info.value.excluded if "cooldown" in r.reason]) == 2


# ------------------------------------------------------ 5. explicit provider + model ---


def test_explicit_provider_and_model_still_work_and_never_outrank_availability() -> None:
    w = World(["alpha", "beta"])
    policy = ExplicitModelPolicy(type="explicit_model", model_id="shared-model", provider_id="beta")
    decision = w.route(policy)
    assert w.key_of(decision.selected.provider_id) == "beta"
    assert decision.fallback_candidates == []  # explicit provider narrows the set
    w.board.record_error(
        provider_id=w.by_key["beta"].id,
        model_id=w.model.id,
        error=_err(ProviderErrorCategory.PROVIDER_UNAVAILABLE),
    )
    with pytest.raises(NoEligibleCandidates) as info:
        w.route(policy)
    assert any(r.provider_key == "beta" and "unavailable" in r.reason for r in info.value.excluded)


# ------------------------------------------------------ 6. boundary: normalized only ---


def test_board_holds_only_normalized_signals_never_provider_internals() -> None:
    w = World(["alpha"])
    w.board.record_error(
        provider_id=w.by_key["alpha"].id,
        model_id=w.model.id,
        error=ProviderError(
            category=ProviderErrorCategory.RATE_LIMITED,
            retryable=True,
            retry_after_ms=1_000,
            provider_code="x-ratelimit-account-7-cookie-session-abc",
            safe_message="limited",
        ),
    )
    snapshot = w.board.snapshot()
    assert len(snapshot) == 1
    row = snapshot[0]
    assert set(row) <= {
        "provider_id",
        "model_id",
        "state",
        "reason",
        "cooldown_until",
        "rpm_used",
        "rpm_limit",
        "last_category",
    }
    assert "cookie" not in repr(row) and "account-7" not in repr(row)


# ------------------------------------------------------ 7. bounded routing at scale ---


def test_two_thousand_bindings_route_in_bounded_time() -> None:
    keys = [f"p{i:04d}" for i in range(2000)]
    w = World(keys)
    for i, key in enumerate(keys):
        if i % 2:
            w.board.record_error(
                provider_id=w.by_key[key].id,
                model_id=w.model.id,
                error=_err(
                    ProviderErrorCategory.RATE_LIMITED, retryable=True, retry_after_ms=60_000
                ),
            )
    started = time.perf_counter()
    decision = w.route(AutoModelPolicy(type="auto", allow_fallback=False))
    elapsed = time.perf_counter() - started
    assert decision.selected.model_id == w.model.id
    assert len(decision.excluded) == 1000
    assert elapsed < 2.0, f"routing over 2000 bindings took {elapsed:.2f}s"
