"""Account Pool Manager semantics (T-IMPL-056; 30 §10.3–§10.5, 41 §10).

Hermetic — pure in-memory pools, registries, and InMemoryLeaseManager; no
network, no adapters, NO AI ANYWHERE. That absence IS the 41 §10 exit
criterion ("account selection is fully testable without AI"): this suite
constructs zero adapters and zero transports.

Asserted verbatim rules:

- 30 §10.5: "Never mix platform and user credentials in one account pool"
  (enforced at register time; ownership side may not flip in place).
- 30 §10.3: all seven eligibility filters in documented order — provider
  active / credential active / account lifecycle READY / not in cooldown /
  tenant-user policy allows it / rate limit budget available / model
  binding available.
- CredentialPolicy closed set: platform_only / user_only / prefer_user /
  auto (30 §10.5, 41 §10).
- 11 §5 "Unknown = ineligible": UNKNOWN rate-limit state excludes.
- 30 §10.4 lease flow: eligible → select → acquire lease → release; a
  leased account is skipped, not double-issued; exhaustion raises
  NoEligibleAccount.
- Recorded LRU selection: never-used first, then oldest use, UUID tiebreak.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from core.contracts.domain import (
    AccountHealthState,
    AccountLifecycleState,
    BindingAvailability,
    Credential,
    CredentialPolicy,
    CredentialStatus,
    Model,
    ModelStatus,
    ModelTier,
    OwnerType,
    Provider,
    ProviderAccount,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.provider import (
    ProviderManifest,
    RateLimitState,
    RateLimitStatus,
)
from core.providers import (
    LEASE_RESOURCE_PREFIX,
    AccountPoolManager,
    BindingRegistry,
    DuplicateRegistration,
    NoEligibleAccount,
    PoolOwnershipViolation,
    ProviderRegistry,
    lease_resource_for,
)
from core.runtime.memory import InMemoryLeaseManager


def run[T](coro: Coroutine[object, object, T]) -> T:
    return asyncio.run(coro)


NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


# --- fixtures ----------------------------------------------------------------------


def _manifest(**overrides: object) -> ProviderManifest:
    payload: dict[str, object] = {
        "id": "real_text",
        "name": "Real Text Provider",
        "version": "1.0.0",
        "status": "active",
        "auth": {"types": ["api_key"], "supports_refresh": False},
        "account_pool": {"supported": True},
        "capabilities": {"chat": True},
        "operations": ["generate_text"],
        "models": {"discovery": "static", "static_models": ["real-text-1"]},
        "rate_limits": {"strategy": "provider_defined"},
        "health": {"checks": ["ping"]},
        "errors": {"mapping": "error_map.json"},
    }
    payload.update(overrides)
    return ProviderManifest.model_validate(payload)


def _provider(key: str, status: ProviderStatus = ProviderStatus.ACTIVE) -> Provider:
    return Provider(
        id=uuid4(),
        provider_key=key,
        display_name=key,
        status=status,
        auth_types=["api_key"],
        supports_account_pool=True,
    )


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.FAST,
        modalities=["text"],
        capabilities=["reasoning"],
        status=ModelStatus.ACTIVE,
    )


def _credential(
    provider_id: UUID,
    owner_type: OwnerType = OwnerType.PLATFORM,
    status: CredentialStatus = CredentialStatus.ACTIVE,
) -> Credential:
    return Credential(
        id=uuid4(),
        owner_type=owner_type,
        owner_id=None if owner_type is OwnerType.PLATFORM else uuid4(),
        provider_id=provider_id,
        credential_ref=f"vault://cred/{uuid4()}",
        status=status,
    )


def _account(
    provider_id: UUID,
    credential: Credential,
    lifecycle: AccountLifecycleState = AccountLifecycleState.READY,
    cooldown_until: datetime | None = None,
) -> ProviderAccount:
    return ProviderAccount(
        id=uuid4(),
        provider_id=provider_id,
        credential_id=credential.id,
        owner_type=credential.owner_type,
        lifecycle_state=lifecycle,
        health_state=AccountHealthState.HEALTHY,
        cooldown_until=cooldown_until,
    )


def _manager(
    provider: Provider,
) -> tuple[AccountPoolManager, ProviderRegistry, InMemoryLeaseManager]:
    registry = ProviderRegistry()
    registry.register(provider, _manifest())
    leases = InMemoryLeaseManager()
    manager = AccountPoolManager(registry, leases, now=lambda: NOW)
    return manager, registry, leases


def _registered(
    manager: AccountPoolManager,
    provider: Provider,
    owner_type: OwnerType = OwnerType.PLATFORM,
    lifecycle: AccountLifecycleState = AccountLifecycleState.READY,
    cred_status: CredentialStatus = CredentialStatus.ACTIVE,
    cooldown_until: datetime | None = None,
) -> ProviderAccount:
    credential = _credential(provider.id, owner_type, cred_status)
    account = _account(provider.id, credential, lifecycle, cooldown_until)
    manager.pool_for(provider.id).register(account, credential)
    return account


# --- never-mix rule (30 §10.5) ------------------------------------------------------


def test_pool_rejects_mixing_platform_and_user_accounts() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider, OwnerType.PLATFORM)
    with pytest.raises(PoolOwnershipViolation, match="[Nn]ever mix"):
        _registered(manager, provider, OwnerType.USER)


def test_pool_rejects_mixing_user_then_platform() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider, OwnerType.TENANT)
    with pytest.raises(PoolOwnershipViolation, match="[Nn]ever mix"):
        _registered(manager, provider, OwnerType.PLATFORM)


def test_tenant_and_user_accounts_share_the_user_side() -> None:
    # 41 §10 split: tenant + user are one side; both may share a pool.
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider, OwnerType.TENANT)
    _registered(manager, provider, OwnerType.USER)
    assert len(manager.pool_for(provider.id).all_accounts()) == 2


def test_pool_rejects_account_of_another_provider() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    other_id = uuid4()
    credential = _credential(other_id)
    account = _account(other_id, credential)
    with pytest.raises(PoolOwnershipViolation, match="belongs to provider"):
        manager.pool_for(provider.id).register(account, credential)


def test_pool_rejects_credential_identity_mismatch() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    credential = _credential(provider.id)
    account = _account(provider.id, credential)
    with pytest.raises(PoolOwnershipViolation, match="does not reference"):
        manager.pool_for(provider.id).register(account, _credential(provider.id))


def test_duplicate_account_registration_is_rejected() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    credential = _credential(provider.id)
    account = _account(provider.id, credential)
    pool = manager.pool_for(provider.id)
    pool.register(account, credential)
    with pytest.raises(DuplicateRegistration):
        pool.register(account, credential)


def test_replace_account_cannot_flip_ownership_side() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider, OwnerType.PLATFORM)
    flipped = account.model_copy(update={"owner_type": OwnerType.USER})
    with pytest.raises(PoolOwnershipViolation, match="cannot change"):
        manager.pool_for(provider.id).replace_account(flipped)


def test_replace_account_updates_lifecycle_in_place() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    updated = account.model_copy(
        update={"lifecycle_state": AccountLifecycleState.COOLDOWN}
    )
    pool = manager.pool_for(provider.id)
    pool.replace_account(updated)
    assert pool.get(account.id).lifecycle_state is AccountLifecycleState.COOLDOWN


# --- 30 §10.3 eligibility filters, one per filter ------------------------------------


def test_filter_1_inactive_provider_yields_no_accounts() -> None:
    provider = _provider("real_text", status=ProviderStatus.DISABLED)
    manager, _, _ = _manager(provider)
    _registered(manager, provider)
    assert manager.eligible_accounts("real_text") == []


def test_filter_2_inactive_credential_excludes_account() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider, cred_status=CredentialStatus.REVOKED)
    ok = _registered(manager, provider)
    assert manager.eligible_accounts("real_text") == [ok]


def test_filter_3_non_ready_lifecycle_excludes_account() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    for state in AccountLifecycleState:
        if state is AccountLifecycleState.READY:
            continue
        _registered(manager, provider, lifecycle=state)
    ready = _registered(manager, provider)
    assert manager.eligible_accounts("real_text") == [ready]


def test_filter_4_active_cooldown_excludes_elapsed_admits() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider, cooldown_until=NOW + timedelta(minutes=5))
    elapsed = _registered(manager, provider, cooldown_until=NOW - timedelta(minutes=5))
    assert manager.eligible_accounts("real_text") == [elapsed]


def test_filter_5_platform_only_policy_excludes_user_side() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    platform = _registered(manager, provider, OwnerType.PLATFORM)
    assert manager.eligible_accounts(
        "real_text", policy=CredentialPolicy.PLATFORM_ONLY
    ) == [platform]
    assert (
        manager.eligible_accounts("real_text", policy=CredentialPolicy.USER_ONLY)
        == []
    )


def test_filter_5_user_only_policy_excludes_platform() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    user = _registered(manager, provider, OwnerType.USER)
    assert manager.eligible_accounts(
        "real_text", policy=CredentialPolicy.USER_ONLY
    ) == [user]
    assert (
        manager.eligible_accounts("real_text", policy=CredentialPolicy.PLATFORM_ONLY)
        == []
    )


def test_filter_6_limited_rate_state_excludes() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    limits = {account.id: RateLimitStatus(state=RateLimitState.LIMITED)}
    assert manager.eligible_accounts("real_text", rate_limits=limits) == []


def test_filter_6_unknown_rate_state_excludes() -> None:
    # 11 §5 "Unknown = ineligible" — deny by default.
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    limits = {account.id: RateLimitStatus(state=RateLimitState.UNKNOWN)}
    assert manager.eligible_accounts("real_text", rate_limits=limits) == []


def test_filter_6_cooldown_until_elapsed_vs_not() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    active = {
        account.id: RateLimitStatus(
            state=RateLimitState.COOLDOWN_UNTIL,
            cooldown_until=NOW + timedelta(minutes=1),
        )
    }
    assert manager.eligible_accounts("real_text", rate_limits=active) == []
    elapsed = {
        account.id: RateLimitStatus(
            state=RateLimitState.COOLDOWN_UNTIL,
            cooldown_until=NOW - timedelta(minutes=1),
        )
    }
    assert manager.eligible_accounts("real_text", rate_limits=elapsed) == [account]


def test_filter_6_available_state_and_absent_report_admit() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    available = {account.id: RateLimitStatus(state=RateLimitState.AVAILABLE)}
    assert manager.eligible_accounts("real_text", rate_limits=available) == [account]
    # Absent report: no budget evidence claims otherwise (recorded posture).
    assert manager.eligible_accounts("real_text", rate_limits={}) == [account]


def test_filter_7_missing_binding_excludes() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider)
    model = _model("real-text-1")
    assert (
        manager.eligible_accounts(
            "real_text", bindings=BindingRegistry(), model_id=model.id
        )
        == []
    )


def test_filter_7_unavailable_binding_excludes_available_admits() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    model = _model("real-text-1")

    for availability, expected in (
        (BindingAvailability.UNAVAILABLE, []),
        (BindingAvailability.DEGRADED, []),
        (BindingAvailability.AVAILABLE, [account]),
    ):
        bindings = BindingRegistry()
        bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name="real-text-1",
                availability=availability,
            )
        )
        assert (
            manager.eligible_accounts(
                "real_text", bindings=bindings, model_id=model.id
            )
            == expected
        )


# --- policy ordering + LRU selection --------------------------------------------------


def test_prefer_user_orders_user_side_before_platform() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    # Never-mix means one pool cannot hold both sides; prefer_user ordering
    # is observable only across the admitted side — assert it filters
    # nothing and orders the user side first when the pool IS user-side.
    user_a = _registered(manager, provider, OwnerType.USER)
    tenant_b = _registered(manager, provider, OwnerType.TENANT)
    result = manager.eligible_accounts(
        "real_text", policy=CredentialPolicy.PREFER_USER
    )
    assert set(a.id for a in result) == {user_a.id, tenant_b.id}
    assert all(a.owner_type in {OwnerType.USER, OwnerType.TENANT} for a in result)


def test_prefer_user_admits_platform_pool_too() -> None:
    # prefer_user ORDERS, it does not filter (recorded semantics).
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    platform = _registered(manager, provider, OwnerType.PLATFORM)
    assert manager.eligible_accounts(
        "real_text", policy=CredentialPolicy.PREFER_USER
    ) == [platform]


def test_lru_selection_never_used_first_then_oldest() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    a = _registered(manager, provider)
    b = _registered(manager, provider)
    c = _registered(manager, provider)

    # Fresh pool: deterministic UUID-string tiebreak.
    baseline = manager.eligible_accounts("real_text")
    assert baseline == sorted(baseline, key=lambda acc: str(acc.id))

    first, lease1 = run(manager.acquire_account("real_text", "w1", 30.0))
    run(manager.release_account(lease1))
    second, lease2 = run(manager.acquire_account("real_text", "w1", 30.0))
    run(manager.release_account(lease2))
    assert first.id != second.id

    # The two used accounts now sort AFTER the never-used one.
    ordered = manager.eligible_accounts("real_text")
    used = {first.id, second.id}
    (never_used,) = [acc for acc in (a, b, c) if acc.id not in used]
    assert ordered[0].id == never_used.id
    # And the least-recently-used of the used pair comes before the other.
    assert ordered[1].id == first.id
    assert ordered[2].id == second.id


def test_select_account_raises_when_none_eligible() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    with pytest.raises(NoEligibleAccount):
        manager.select_account("real_text")


def test_select_account_returns_first_ordered_candidate() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider)
    _registered(manager, provider)
    assert (
        manager.select_account("real_text")
        == manager.eligible_accounts("real_text")[0]
    )


# --- 30 §10.4 lease flow ---------------------------------------------------------------


def test_acquire_returns_account_with_lease_on_its_resource() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    got, lease = run(manager.acquire_account("real_text", "worker-1", 30.0))
    assert got.id == account.id
    assert lease.resource == lease_resource_for(account.id)
    assert lease.resource.startswith(LEASE_RESOURCE_PREFIX)
    assert lease.owner == "worker-1"
    assert lease.fencing_token >= 1


def test_leased_account_is_skipped_not_double_issued() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider)
    _registered(manager, provider)

    first, _ = run(manager.acquire_account("real_text", "w1", 30.0))
    second, _ = run(manager.acquire_account("real_text", "w2", 30.0))
    assert first.id != second.id


def test_all_accounts_leased_raises_no_eligible() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    _registered(manager, provider)
    run(manager.acquire_account("real_text", "w1", 30.0))
    with pytest.raises(NoEligibleAccount, match="leasable"):
        run(manager.acquire_account("real_text", "w2", 30.0))


def test_release_makes_account_leasable_again() -> None:
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    _, lease = run(manager.acquire_account("real_text", "w1", 30.0))
    run(manager.release_account(lease))
    again, lease2 = run(manager.acquire_account("real_text", "w2", 30.0))
    assert again.id == account.id
    # Fencing tokens strictly increase across acquisitions (40 §4.4).
    assert lease2.fencing_token > lease.fencing_token


def test_full_lease_flow_with_state_update() -> None:
    # 30 §10.4: eligible → select → lease → execute → update state → release.
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)

    got, lease = run(manager.acquire_account("real_text", "w1", 30.0))
    # (execute happens here — no AI in this suite, by design)
    cooled = got.model_copy(
        update={
            "lifecycle_state": AccountLifecycleState.COOLDOWN,
            "cooldown_until": NOW + timedelta(minutes=10),
        }
    )
    manager.pool_for(provider.id).replace_account(cooled)
    run(manager.release_account(lease))

    # Post-update the account is no longer eligible (filters 3+4).
    assert manager.eligible_accounts("real_text") == []
    assert (
        manager.pool_for(provider.id).get(account.id).lifecycle_state
        is AccountLifecycleState.COOLDOWN
    )


# --- 41 §10 exit criterion -------------------------------------------------------------


def test_exit_criterion_selection_requires_no_ai_module() -> None:
    """41 §10 exit: 'account selection is fully testable without AI.'

    Constructive proof: a full eligibility + selection + lease round-trip
    using ONLY contracts, registries, pools, and the in-memory lease
    manager — no adapter, no transport, no AI import anywhere in this file.
    """
    provider = _provider("real_text")
    manager, _, _ = _manager(provider)
    account = _registered(manager, provider)
    model = _model("real-text-1")
    bindings = BindingRegistry()
    bindings.register(
        ProviderModelBinding(
            provider_id=provider.id,
            model_id=model.id,
            provider_model_name="real-text-1",
            availability=BindingAvailability.AVAILABLE,
        )
    )
    limits = {account.id: RateLimitStatus(state=RateLimitState.AVAILABLE)}

    selected = manager.select_account(
        "real_text",
        policy=CredentialPolicy.PLATFORM_ONLY,
        rate_limits=limits,
        bindings=bindings,
        model_id=model.id,
    )
    got, lease = run(
        manager.acquire_account(
            "real_text",
            "worker-1",
            30.0,
            policy=CredentialPolicy.PLATFORM_ONLY,
            rate_limits=limits,
            bindings=bindings,
            model_id=model.id,
        )
    )
    assert selected.id == got.id == account.id
    run(manager.release_account(lease))
