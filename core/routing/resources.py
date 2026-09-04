"""Resource Selector — the 11 §2 "Provider/Account Selection" stage
(41 §11 "Resource Selector").

Fills the nullable ``account_id`` on the routing decision's candidate by
consulting the Phase 7 :class:`AccountPoolManager` (30 §10.3 eligibility),
walking the ranked candidates in decision order.

Recorded derivation decisions (never silent):

- DECIDE, NOT EXECUTE: the Router "DOES: decide / DOES NOT: execute"
  (41 §11) — this stage SELECTS an account; acquiring the LEASE is the
  execution flow's job (30 §10.4 steps 3-6, ``acquire_account`` at execution
  time). No lease is taken here, so a decision remains a pure, side-effect-
  free artifact.
- POOLS ARE OPTIONAL (30 §10.1): a provider whose manifest declares
  ``account_pool.supported: false`` is admitted WITHOUT an account
  (``account_id`` stays None) — that is a valid, complete selection for
  pool-less providers. A provider that DECLARES pool support must yield an
  eligible account or the candidate is skipped (11 §14 steps 6-7: "Select
  eligible account/credential; if no eligible route" => next/fail).
- WALK ORDER: ``decision.ranked`` best-first (the router's deterministic
  order) — the first candidate that is resource-complete wins; skipped
  candidates get explainable records appended (11 §5 explainability).
- FAIL CLEARLY: all candidates exhausted => :class:`NoEligibleAccount`
  (reused from core/providers — same failure domain), carrying the skip
  records.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.domain import CredentialPolicy
from core.contracts.provider import RateLimitStatus
from core.contracts.routing import CandidateScore, ExclusionRecord, RoutingDecision
from core.providers.accounts import AccountPoolManager
from core.providers.errors import NoEligibleAccount
from core.providers.registry import BindingRegistry, ProviderRegistry


class ResourceSelector:
    """Provider/Account Selection stage (11 §2) — pure selection, no leases."""

    def __init__(
        self,
        providers: ProviderRegistry,
        accounts: AccountPoolManager,
    ) -> None:
        self._providers = providers
        self._accounts = accounts

    def select(
        self,
        decision: RoutingDecision,
        *,
        policy: CredentialPolicy = CredentialPolicy.AUTO,
        rate_limits: dict[UUID, RateLimitStatus] | None = None,
        bindings: BindingRegistry | None = None,
    ) -> CandidateScore:
        """Return the first ranked candidate completed with its resources.

        ``account_id`` is filled for pooled providers and stays ``None`` for
        pool-less providers (30 §10.1). Raises :class:`NoEligibleAccount`
        when every pooled candidate lacks an eligible account.
        """
        skipped: list[ExclusionRecord] = []
        for candidate in decision.ranked:
            entry = self._providers.get_by_id(candidate.provider_id)
            if not entry.manifest.account_pool.supported:
                # Pool-less provider: selection is complete without an account.
                return candidate
            try:
                account = self._accounts.select_account(
                    entry.provider.provider_key,
                    policy=policy,
                    rate_limits=rate_limits,
                    bindings=bindings,
                    model_id=candidate.model_id,
                )
            except NoEligibleAccount as exc:
                skipped.append(
                    ExclusionRecord(
                        model_key=str(candidate.model_id),
                        provider_key=entry.provider.provider_key,
                        reason=f"no eligible account: {exc}",
                    )
                )
                continue
            return candidate.model_copy(update={"account_id": account.id})
        reasons = "; ".join(record.reason for record in skipped) or "no candidates"
        msg = f"no candidate could be resource-completed (11 §2/§14): {reasons}"
        raise NoEligibleAccount(msg)

    def complete(
        self,
        decision: RoutingDecision,
        *,
        policy: CredentialPolicy | None = None,
        rate_limits: dict[UUID, RateLimitStatus] | None = None,
        bindings: BindingRegistry | None = None,
    ) -> RoutingDecision:
        """Return an ACCOUNT-COMPLETE decision (R168 D-03/D-04).

        Every pooled candidate in ``decision.ranked`` is expanded into one
        candidate PER ELIGIBLE ACCOUNT (LRU order from
        :meth:`AccountPoolManager.eligible_accounts`, filtered by ``policy``
        — 30 §10), so the Execution Service's failover walk
        ``[selected, *fallback_candidates]`` naturally tries a second account
        of the SAME provider before moving to the next provider. Pool-less
        providers pass through untouched (30 §10.1). Pooled candidates with
        no eligible account are recorded in ``excluded``. Raises
        :class:`NoEligibleAccount` when nothing survives.
        """
        effective = policy if policy is not None else CredentialPolicy.AUTO
        route: list[CandidateScore] = []
        skipped: list[ExclusionRecord] = []
        for candidate in decision.ranked:
            entry = self._providers.get_by_id(candidate.provider_id)
            if not entry.manifest.account_pool.supported:
                route.append(candidate)
                continue
            accounts = self._accounts.eligible_accounts(
                entry.provider.provider_key,
                policy=effective,
                rate_limits=rate_limits,
                bindings=bindings,
                model_id=candidate.model_id,
            )
            if not accounts:
                skipped.append(
                    ExclusionRecord(
                        model_key=str(candidate.model_id),
                        provider_key=entry.provider.provider_key,
                        reason=f"no eligible account under policy {effective.value}",
                    )
                )
                continue
            route.extend(
                candidate.model_copy(update={"account_id": account.id}) for account in accounts
            )
        if not route:
            reasons = "; ".join(record.reason for record in skipped) or "no candidates"
            msg = f"no candidate could be resource-completed (11 §2/§14): {reasons}"
            raise NoEligibleAccount(msg)
        return decision.model_copy(
            update={
                "selected": route[0],
                "ranked": route,
                "fallback_candidates": route[1:],
                "excluded": [*decision.excluded, *skipped],
            }
        )
