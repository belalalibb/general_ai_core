"""D-03 / D-04 (R168 Round B) — hermetic two-account failover on ONE provider.

Defect ledger D-03: an account pool exists (core/providers/accounts.py) but no
call site completes a route with ``account_id``; execution resolves ONE
credential_ref per provider, so two credentials of the same provider are
"NOT SUPPORTED BY CURRENT CONTRACT" (certification MATRIX row
``two_credentials_same_provider``). D-04: ``CredentialPolicy`` never reaches
the router request and ``PROVIDER_ACCOUNT_USED`` is never emitted.

The three links this file proves (30 §10, 11 §2/§14, 20 §5, 21 §8):

1. ``RoutingRequest.credential_policy`` is carried through the request and
   applied by the Resource Selector (PLATFORM_ONLY excludes USER accounts).
2. ``ResourceSelector.complete`` turns a router decision into an account-
   complete route: one candidate per eligible account (LRU order), the first
   is ``selected`` and the rest are ``fallback_candidates`` — a second
   account of the SAME provider is a real failover target.
3. ``ExecutionService`` resolves the credential_ref PER ACCOUNT (refs minted
   by a SecretManagerPort — the secret value never leaves the manager) and
   appends ``PROVIDER_ACCOUNT_USED`` for every account attempt, secret-free.

Hermetic: fake adapter, in-memory secret manager / lease manager / audit log.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.domain import (
    AccountHealthState,
    AccountLifecycleState,
    BindingAvailability,
    Credential,
    CredentialPolicy,
    Model,
    ModelStatus,
    ModelTier,
    OwnerType,
    Provider,
    ProviderAccount,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.model_policy import AutoModelPolicy
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
from core.contracts.routing import RoutingDecision, RoutingRequest
from core.execution import ExecutionService
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.providers.accounts import AccountPoolManager
from core.routing.resources import ResourceSelector
from core.routing.router import SimpleScoringRouter
from core.runtime.memory import InMemoryLeaseManager
from core.secrets.memory import InMemorySecretManager
from core.usage import InMemoryUsageAccounting


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


def _err(category: ProviderErrorCategory, *, retryable: bool = False) -> ProviderError:
    return ProviderError(category=category, retryable=retryable, safe_message=f"fake {category}")


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


def _manifest(key: str, *, pooled: bool) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": key,
            "name": key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": pooled},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
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


PLATFORM_TENANT = uuid4()


class World:
    """ONE pooled provider, N accounts, each with its own SecretManager-minted ref."""

    def __init__(self, *, pooled: bool = True) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.secrets = InMemorySecretManager()
        self.leases = InMemoryLeaseManager()
        self.audit = InMemoryAuditLog()
        self.usage = InMemoryUsageAccounting()
        self.accounts = AccountPoolManager(self.providers, self.leases)
        self.adapters: dict[UUID, ScriptedAdapter] = {}
        self.credential_refs: dict[UUID, str] = {}
        self.account_credentials: dict[UUID, str] = {}
        self.secret_values: dict[UUID, str] = {}

        self.provider = Provider(
            id=uuid4(),
            provider_key="pooled",
            display_name="pooled",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=pooled,
        )
        self.providers.register(self.provider, _manifest("pooled", pooled=pooled))
        self.model = _model("m-1")
        self.models.register(self.model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=self.provider.id,
                model_id=self.model.id,
                provider_model_name="vendor/m-1",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        self.adapter = ScriptedAdapter()
        self.adapters[self.provider.id] = self.adapter

    def account(
        self, secret_value: str, *, owner: OwnerType = OwnerType.PLATFORM
    ) -> ProviderAccount:
        ref = self.secrets.store(PLATFORM_TENANT, secret_value)
        credential = Credential(
            id=uuid4(),
            owner_type=owner,
            owner_id=None if owner is OwnerType.PLATFORM else uuid4(),
            provider_id=self.provider.id,
            credential_ref=ref,
            status=CredentialStatus.ACTIVE,
        )
        account = ProviderAccount(
            id=uuid4(),
            provider_id=self.provider.id,
            credential_id=credential.id,
            owner_type=owner,
            lifecycle_state=AccountLifecycleState.READY,
            health_state=AccountHealthState.HEALTHY,
        )
        self.accounts.pool_for(self.provider.id).register(account, credential)
        self.account_credentials[account.id] = ref
        self.secret_values[account.id] = secret_value
        return account

    def request(self, policy: CredentialPolicy | None) -> RoutingRequest:
        kwargs: dict[str, Any] = {
            "operation": ProviderOperation.GENERATE_TEXT,
            "model_policy": AutoModelPolicy(type="auto"),
        }
        if policy is not None:
            kwargs["credential_policy"] = policy
        return RoutingRequest(**kwargs)

    def complete(self, policy: CredentialPolicy = CredentialPolicy.AUTO) -> RoutingDecision:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        decision = router.route(self.request(policy))
        selector = ResourceSelector(self.providers, self.accounts)
        return selector.complete(decision, policy=policy, bindings=self.bindings)

    def service(self) -> ExecutionService:
        return ExecutionService(
            adapters=self.adapters,
            credential_refs=self.credential_refs,
            bindings=self.bindings,
            max_retries_per_candidate=1,
            usage=self.usage,
            sleeper=_no_sleep,
            account_credentials=self.account_credentials,
            audit=self.audit,
        )

    def execute(self, decision: RoutingDecision) -> tuple[UUID, Any]:
        tenant_id = uuid4()
        self.usage.configure_tenant(tenant_id, plan="test", task_units_limit=100)
        report = run(
            self.service().execute_single(
                tenant_id=tenant_id,
                user_id=uuid4(),
                decision=decision,
                operation=ProviderOperation.GENERATE_TEXT,
                payload={"ask": "hi"},
                request_hash="h",
            )
        )
        return tenant_id, report


def test_routing_request_carries_credential_policy() -> None:
    world = World()
    request = world.request(CredentialPolicy.PLATFORM_ONLY)
    assert request.credential_policy is CredentialPolicy.PLATFORM_ONLY
    assert world.request(None).credential_policy is None


def test_credential_policy_is_applied_by_completion() -> None:
    """A pool is single-sided (30 §10.5), so the policy filter is proven on a
    USER-side pool: USER_ONLY admits it, PLATFORM_ONLY excludes it entirely."""
    from core.providers.errors import NoEligibleAccount

    world = World()
    user = world.account("sk-user", owner=OwnerType.USER)
    decision = world.complete(CredentialPolicy.USER_ONLY)
    ids = [c.account_id for c in [decision.selected, *decision.fallback_candidates]]
    assert ids == [user.id]
    with pytest.raises(NoEligibleAccount):
        world.complete(CredentialPolicy.PLATFORM_ONLY)


def test_complete_expands_pooled_provider_into_two_account_candidates() -> None:
    world = World()
    a1 = world.account("sk-1")
    a2 = world.account("sk-2")
    decision = world.complete()
    route = [decision.selected, *decision.fallback_candidates]
    assert len(route) == 2
    assert {c.account_id for c in route} == {a1.id, a2.id}
    assert all(c.provider_id == world.provider.id for c in route)
    assert decision.selected is decision.ranked[0]
    assert len(decision.ranked) == 2


def test_complete_leaves_pool_less_provider_untouched() -> None:
    world = World(pooled=False)
    world.credential_refs[world.provider.id] = "secret-ref://pooled"
    decision = world.complete()
    assert decision.selected.account_id is None
    assert decision.fallback_candidates == []


def test_two_accounts_same_provider_fail_over_with_distinct_refs_and_audit() -> None:
    world = World()
    world.account("sk-1")
    world.account("sk-2")
    world.adapter.script = [_err(ProviderErrorCategory.INVALID_CREDENTIAL), {"ok": True}]

    decision = world.complete(CredentialPolicy.PLATFORM_ONLY)
    tenant_id, report = world.execute(decision)

    attempts = report.nodes[0].attempts
    assert [a.succeeded for a in attempts] == [False, True]
    first, second = (a.candidate.account_id for a in attempts)
    assert first is not None and second is not None and first != second

    reqs = world.adapter.requests
    assert [r.account_id for r in reqs] == [first, second]
    assert reqs[0].credential_ref == world.account_credentials[first]
    assert reqs[1].credential_ref == world.account_credentials[second]
    assert reqs[0].credential_ref != reqs[1].credential_ref
    resolved = world.secrets.resolve(PLATFORM_TENANT, reqs[1].credential_ref)
    assert resolved == world.secret_values[second]
    for req in reqs:
        assert "sk-" not in req.credential_ref

    used = world.audit.read(tenant_id, event_type=AuditEventType.PROVIDER_ACCOUNT_USED)
    assert [UUID(str(e.details["account_id"])) for e in used] == [first, second]
    assert [e.details["succeeded"] for e in used] == [False, True]
    dumped = json.dumps([e.model_dump(mode="json") for e in used])
    assert "sk-1" not in dumped and "sk-2" not in dumped


def test_account_completed_route_needs_no_provider_level_credential() -> None:
    """Composition validation accepts a route whose credentials are per-account."""
    world = World()
    world.account("sk-1")
    decision = world.complete()
    assert world.credential_refs == {}
    _, report = world.execute(decision)
    assert report.nodes[0].attempts[0].succeeded is True


def test_no_eligible_account_fails_clearly() -> None:
    from core.providers.errors import NoEligibleAccount

    world = World()
    world.account("sk-user", owner=OwnerType.USER)
    with pytest.raises(NoEligibleAccount):
        world.complete(CredentialPolicy.PLATFORM_ONLY)
