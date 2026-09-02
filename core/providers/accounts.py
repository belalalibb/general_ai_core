"""Account Pool Manager — eligibility filtering, selection, and leased
execution flow for provider accounts (30 §10.3–§10.5, 41 §10).

FINAL Phase 7 (T-IMPL-056). Spec anchors:

- 30 §10.1: account pools are OPTIONAL per provider — this manager exists
  for providers that declare one; providers without pools never touch it.
- 30 §10.3: "Core asks Account Pool Manager for an eligible account."
  Eligibility filters (verbatim list): provider active / credential active /
  account lifecycle READY / not in cooldown / tenant-user policy allows it /
  rate limit budget available / model binding available.
- 30 §10.4: concurrent execution must use leases — eligible accounts →
  select → acquire lease → execute → update state → release.
- 30 §10.5: "Never mix platform and user credentials in one account pool"
  + the credential policy closed set (platform_only/user_only/prefer_user/
  auto — ``CredentialPolicy`` in core/contracts/domain.py).
- 41 §10 exit: "account selection is fully testable without AI" — this
  module is pure coordination; no adapter, no network, no AI anywhere.

Recorded derivation decisions (never silent):

- SELECTION ORDER: 30 §10.3 says selection "MAY consider" LRU/quota/health/
  latency/error-rate/priority/owner-policy — the spec mandates NO specific
  strategy, so the manager selects LEAST RECENTLY USED (first listed
  consideration) deterministically, and the strategy is a seam
  (``select_key``) callers may replace. Nothing beyond LRU is invented.
- POLICY FILTER SEMANTICS: per the ``CredentialPolicy`` recorded reading
  (41 §10 ownership split), ``platform_only`` admits OwnerType.PLATFORM
  accounts; ``user_only`` admits TENANT and USER accounts; ``prefer_user``
  admits both sides but orders the user side first; ``auto`` admits both
  with no ordering preference (spec states none).
- RATE-LIMIT FILTER: the 30 §10.3 "rate limit budget available" filter is
  evaluated from the account's normalized rate-limit state (30 §12) as
  reported by the caller: ``limited`` and un-elapsed ``cooldown_until``
  exclude; ``unknown`` EXCLUDES (11 §5 "Unknown = ineligible" — deny by
  default); absence of a report means no limit evidence, which admits
  (the filter checks "budget available", and no budget system claims
  otherwise — same posture as aggregate_provider_health's "absence of
  accounts is not evidence").
- MODEL-BINDING FILTER: applied only when the caller passes a
  ``BindingRegistry`` + model_id (the filter is per-request context; the
  pool itself is model-agnostic).
- NEVER-MIX ENFORCEMENT: the pool REJECTS registering platform-owned and
  user-side accounts into the same pool (30 §10.5 verbatim) — a data rule,
  enforced at write time, not a runtime branch.
- LEASE RESOURCE KEY: ``provider_account:{account_id}`` — accounts are
  exactly the "exclusive resources" the LeasePort exists for (40 §4.4,
  recorded in core/runtime/ports.py: "provider accounts, credentials").
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import UUID

from core.contracts.domain import (
    AccountLifecycleState,
    BindingAvailability,
    Credential,
    CredentialPolicy,
    CredentialStatus,
    OwnerType,
    ProviderAccount,
)
from core.contracts.provider import RateLimitState, RateLimitStatus
from core.providers.errors import (
    BindingNotFound,
    DuplicateRegistration,
    NoEligibleAccount,
    PoolOwnershipViolation,
)
from core.providers.registry import BindingRegistry, ProviderRegistry
from core.runtime.ports import Lease, LeasePort

#: Owner types on the "user side" of the 41 §10 ownership split.
_USER_SIDE: frozenset[OwnerType] = frozenset({OwnerType.TENANT, OwnerType.USER})

#: Lease resource-key prefix for provider accounts (40 §4.4 exclusive resources).
LEASE_RESOURCE_PREFIX = "provider_account:"


def lease_resource_for(account_id: UUID) -> str:
    """The LeasePort resource key for one provider account."""
    return f"{LEASE_RESOURCE_PREFIX}{account_id}"


class AccountPool:
    """One provider's account pool (30 §10.1) — in-memory, hermetic.

    Enforces the 30 §10.5 never-mix rule at registration time: a pool holds
    EITHER platform-owned accounts OR user-side (tenant/user) accounts,
    never both.
    """

    def __init__(self, provider_id: UUID) -> None:
        self.provider_id = provider_id
        self._accounts: dict[UUID, ProviderAccount] = {}
        self._credentials: dict[UUID, Credential] = {}
        self._side: OwnerType | None = None  # PLATFORM or (representative) user side

    def register(self, account: ProviderAccount, credential: Credential) -> None:
        """Add an account + its credential record to the pool.

        Raises :class:`PoolOwnershipViolation` on a 30 §10.5 mix, and
        :class:`DuplicateRegistration` on identity reuse.
        """
        if account.provider_id != self.provider_id:
            msg = (
                f"account {account.id} belongs to provider {account.provider_id},"
                f" not {self.provider_id}"
            )
            raise PoolOwnershipViolation(msg)
        if account.credential_id != credential.id:
            msg = f"account {account.id} does not reference credential {credential.id}"
            raise PoolOwnershipViolation(msg)
        incoming_is_platform = account.owner_type is OwnerType.PLATFORM
        if self._side is not None:
            pool_is_platform = self._side is OwnerType.PLATFORM
            if pool_is_platform != incoming_is_platform:
                msg = "never mix platform and user credentials in one account pool (30 §10.5)"
                raise PoolOwnershipViolation(msg)
        if account.id in self._accounts:
            msg = f"account already registered: {account.id}"
            raise DuplicateRegistration(msg)
        self._accounts[account.id] = account
        self._credentials[account.id] = credential
        if self._side is None:
            self._side = OwnerType.PLATFORM if incoming_is_platform else account.owner_type

    def replace_account(self, account: ProviderAccount) -> None:
        """Update a registered account's record (lifecycle transitions).

        Ownership side may not change (that would be a re-pool, not an
        update); the credential record is kept.
        """
        existing = self._accounts.get(account.id)
        if existing is None:
            msg = f"account not registered: {account.id}"
            raise NoEligibleAccount(msg)
        was_platform = existing.owner_type is OwnerType.PLATFORM
        now_platform = account.owner_type is OwnerType.PLATFORM
        if was_platform != now_platform:
            msg = "account ownership side cannot change in place (30 §10.5)"
            raise PoolOwnershipViolation(msg)
        self._accounts[account.id] = account

    def get(self, account_id: UUID) -> ProviderAccount:
        account = self._accounts.get(account_id)
        if account is None:
            msg = f"account not registered: {account_id}"
            raise NoEligibleAccount(msg)
        return account

    def credential_for(self, account_id: UUID) -> Credential:
        credential = self._credentials.get(account_id)
        if credential is None:
            msg = f"account not registered: {account_id}"
            raise NoEligibleAccount(msg)
        return credential

    def all_accounts(self) -> list[ProviderAccount]:
        return list(self._accounts.values())


class AccountPoolManager:
    """Account eligibility + selection + leased-execution coordinator
    (30 §10.3–§10.4).

    Pure coordination: consumes registry eligibility answers and pool data;
    performs no I/O of its own besides the injected LeasePort. Fully
    testable without AI (41 §10 exit criterion).
    """

    def __init__(
        self,
        providers: ProviderRegistry,
        leases: LeasePort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._providers = providers
        self._leases = leases
        self._now = now if now is not None else lambda: datetime.now(tz=UTC)
        self._pools: dict[UUID, AccountPool] = {}
        # LRU bookkeeping: account_id -> monotonically increasing use stamp.
        self._use_seq = 0
        self._last_used: dict[UUID, int] = {}

    # -- pool management ---------------------------------------------------------

    def pool_for(self, provider_id: UUID) -> AccountPool:
        pool = self._pools.get(provider_id)
        if pool is None:
            pool = AccountPool(provider_id)
            self._pools[provider_id] = pool
        return pool

    # -- eligibility (30 §10.3 filters, in the documented order) -------------------

    def eligible_accounts(
        self,
        provider_key: str,
        *,
        policy: CredentialPolicy = CredentialPolicy.AUTO,
        rate_limits: dict[UUID, RateLimitStatus] | None = None,
        bindings: BindingRegistry | None = None,
        model_id: UUID | None = None,
    ) -> list[ProviderAccount]:
        """Return eligible accounts, ordered for selection.

        Applies the 30 §10.3 filters in the documented order. Ordering:
        policy-preferred side first (prefer_user), then least recently used
        (recorded selection strategy).
        """
        # Filter 1: provider active (registry eligibility answer, never re-derived).
        entry = self._providers.get(provider_key)
        if not entry.is_routable:
            return []
        pool = self._pools.get(entry.provider.id)
        if pool is None:
            return []

        limits = rate_limits or {}
        now = self._now()
        out: list[ProviderAccount] = []
        for account in pool.all_accounts():
            # Filter 2: credential active.
            credential = pool.credential_for(account.id)
            if credential.status is not CredentialStatus.ACTIVE:
                continue
            # Filter 3: account lifecycle READY.
            if account.lifecycle_state is not AccountLifecycleState.READY:
                continue
            # Filter 4: not in cooldown.
            if account.cooldown_until is not None and account.cooldown_until > now:
                continue
            # Filter 5: tenant/user policy allows it (CredentialPolicy).
            if not _policy_admits(policy, account.owner_type):
                continue
            # Filter 6: rate limit budget available (30 §12 normalized state;
            # unknown => ineligible, 11 §5).
            status = limits.get(account.id)
            if status is not None and not _budget_available(status, now):
                continue
            # Filter 7: model binding available (per-request context).
            if bindings is not None and model_id is not None:
                try:
                    binding = bindings.get(entry.provider.id, model_id)
                except BindingNotFound:
                    continue  # no binding => ineligible for this model
                if binding.availability is not BindingAvailability.AVAILABLE:
                    continue
            out.append(account)

        return self._ordered(out, policy)

    def select_account(
        self,
        provider_key: str,
        *,
        policy: CredentialPolicy = CredentialPolicy.AUTO,
        rate_limits: dict[UUID, RateLimitStatus] | None = None,
        bindings: BindingRegistry | None = None,
        model_id: UUID | None = None,
    ) -> ProviderAccount:
        """Select ONE eligible account (30 §10.3) or raise NoEligibleAccount."""
        candidates = self.eligible_accounts(
            provider_key,
            policy=policy,
            rate_limits=rate_limits,
            bindings=bindings,
            model_id=model_id,
        )
        if not candidates:
            msg = f"no eligible account for provider {provider_key!r} (30 §10.3)"
            raise NoEligibleAccount(msg)
        return candidates[0]

    # -- leased acquisition (30 §10.4) ---------------------------------------------

    async def acquire_account(
        self,
        provider_key: str,
        owner: str,
        ttl_seconds: float,
        *,
        policy: CredentialPolicy = CredentialPolicy.AUTO,
        rate_limits: dict[UUID, RateLimitStatus] | None = None,
        bindings: BindingRegistry | None = None,
        model_id: UUID | None = None,
    ) -> tuple[ProviderAccount, Lease]:
        """30 §10.4 flow steps 1–3: eligible → select → acquire lease.

        Walks eligible accounts in selection order; an account whose lease
        is held by another live owner is skipped (that is exactly what the
        lease is for), trying the next candidate. Raises NoEligibleAccount
        when no candidate can be both selected and leased.
        """
        candidates = self.eligible_accounts(
            provider_key,
            policy=policy,
            rate_limits=rate_limits,
            bindings=bindings,
            model_id=model_id,
        )
        for account in candidates:
            lease = await self._leases.acquire(lease_resource_for(account.id), owner, ttl_seconds)
            if lease is None:
                continue  # held elsewhere — concurrency working as intended
            self._use_seq += 1
            self._last_used[account.id] = self._use_seq
            return account, lease
        msg = f"no eligible, leasable account for provider {provider_key!r} (30 §10.3/§10.4)"
        raise NoEligibleAccount(msg)

    async def release_account(self, lease: Lease) -> None:
        """30 §10.4 flow step 6: release the lease (state updates are the
        caller's step 5 via ``AccountPool.replace_account``)."""
        await self._leases.release(lease)

    # -- internals ------------------------------------------------------------------

    def _ordered(
        self, accounts: Sequence[ProviderAccount], policy: CredentialPolicy
    ) -> list[ProviderAccount]:
        def lru_key(account: ProviderAccount) -> tuple[int, str]:
            # Never-used accounts (stamp 0) come first; then oldest use;
            # UUID string as the deterministic tiebreaker.
            return (self._last_used.get(account.id, 0), str(account.id))

        ordered = sorted(accounts, key=lru_key)
        if policy is CredentialPolicy.PREFER_USER:
            user_side = [a for a in ordered if a.owner_type in _USER_SIDE]
            platform = [a for a in ordered if a.owner_type is OwnerType.PLATFORM]
            return user_side + platform
        return ordered


def _policy_admits(policy: CredentialPolicy, owner_type: OwnerType) -> bool:
    """CredentialPolicy filter (30 §10.5 closed set; recorded semantics)."""
    if policy is CredentialPolicy.PLATFORM_ONLY:
        return owner_type is OwnerType.PLATFORM
    if policy is CredentialPolicy.USER_ONLY:
        return owner_type in _USER_SIDE
    # prefer_user and auto admit both sides (prefer_user orders, not filters).
    return True


def _budget_available(status: RateLimitStatus, now: datetime) -> bool:
    """30 §10.3 'rate limit budget available' from normalized state (30 §12)."""
    if status.state is RateLimitState.AVAILABLE:
        return True
    if status.state is RateLimitState.LIMITED:
        return False
    if status.state is RateLimitState.COOLDOWN_UNTIL:
        cooldown_until = status.cooldown_until
        return cooldown_until is not None and cooldown_until <= now
    # UNKNOWN: 11 §5 "Unknown = ineligible" — deny by default.
    return False
