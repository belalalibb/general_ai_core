"""Resource signal board — runtime eligibility signals for the ONE router (R188 A1).

Engine/fuel boundary (R188-DEC-01): the Core never learns HOW a provider
manages accounts, sessions, proxies or queues. What crosses the boundary is
the normalized ``ProviderError`` (30 §14) and the provider-declared limit
metadata already carried by ``ProviderModelBinding.limits_metadata``
(03 §4). This module folds those normalized facts into a per-(provider,
model) eligibility answer that the router consumes as ONE MORE hard filter
(11 §5 — the "rate-limit budget" position the router docstring had recorded
as deferred). It is not a second health system and not a second router:

- it produces no decisions (it answers "is this resource eligible NOW, and
  if not, when might it be");
- it stores only normalized categories, timestamps and counters — never a
  provider payload, code, key, account or session (test 6 of the RED module
  asserts the snapshot vocabulary);
- it is process-local by design (same posture as ``InMemoryRateLimiter``);
  a shared store is a composition concern that can bind the same protocol
  later without touching the router.

Signal semantics (recorded, deny-by-default only where the provider said so):

- ``rate_limited`` / ``quota_exceeded`` → cooldown until ``now +
  retry_after_ms`` (or :data:`DEFAULT_COOLDOWN_MS` when the provider gave
  none). A cooldown is a temporary exclusion, never a ban: it expires.
- ``provider_unavailable`` / ``auth_expired`` / ``invalid_credential`` →
  provider-scope unavailability for :data:`DEFAULT_UNAVAILABLE_MS`
  (bounded; a later success clears it immediately).
- any other category → no signal (request-indicting or non-retryable
  failures say nothing about the resource's capacity).
- a SUCCESS clears cooldown/unavailability for that (provider, model).
- RPM: when the binding declares ``limits_metadata["rpm"]`` (an int > 0),
  every attempt counts against a fixed 60 s window; once the count reaches
  the limit the pair is ineligible until the window rolls. Undeclared ⇒ no
  RPM constraint (unknown is not invented, 30 §4.3). Further dimensions
  (tpm, concurrency, …) are additional keys on the same record, not new
  classes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from core.contracts.base import JsonObject, utc_now
from core.contracts.provider import ProviderError, ProviderErrorCategory

#: Cooldown applied when a rate-limit/quota error carries no Retry-After.
DEFAULT_COOLDOWN_MS = 30_000
#: Bounded provider-scope unavailability window after an outage-class error.
DEFAULT_UNAVAILABLE_MS = 60_000
#: Fixed RPM window (requests per MINUTE — the dimension's own definition).
RPM_WINDOW_SECONDS = 60

_COOLDOWN_CATEGORIES: frozenset[ProviderErrorCategory] = frozenset(
    {ProviderErrorCategory.RATE_LIMITED, ProviderErrorCategory.QUOTA_EXCEEDED}
)
_UNAVAILABLE_CATEGORIES: frozenset[ProviderErrorCategory] = frozenset(
    {
        ProviderErrorCategory.PROVIDER_UNAVAILABLE,
        ProviderErrorCategory.AUTH_EXPIRED,
        ProviderErrorCategory.INVALID_CREDENTIAL,
    }
)


@dataclass(frozen=True)
class Eligibility:
    """Answer for one (provider, model) pair at one instant."""

    eligible: bool
    reason: str | None = None
    retry_after_ms: int | None = None


@dataclass
class _Record:
    cooldown_until: datetime | None = None
    unavailable_until: datetime | None = None
    last_category: ProviderErrorCategory | None = None
    window_start: datetime | None = None
    rpm_used: int = 0
    rpm_limit: int | None = None
    extra: dict[str, int] = field(default_factory=dict)


class ResourceSignalPort(Protocol):
    """What the router and the execution service need from a signal store."""

    def eligibility(
        self, provider_id: UUID, model_id: UUID, *, limits: Mapping[str, object] | None = None
    ) -> Eligibility: ...

    def record_attempt(
        self, *, provider_id: UUID, model_id: UUID, limits: Mapping[str, object] | None = None
    ) -> None: ...

    def record_success(self, *, provider_id: UUID, model_id: UUID) -> None: ...

    def record_error(self, *, provider_id: UUID, model_id: UUID, error: ProviderError) -> None: ...


class ResourceSignalBoard:
    """Process-local :class:`ResourceSignalPort` implementation."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = utc_now,
        default_cooldown_ms: int = DEFAULT_COOLDOWN_MS,
        default_unavailable_ms: int = DEFAULT_UNAVAILABLE_MS,
    ) -> None:
        if default_cooldown_ms < 0 or default_unavailable_ms < 0:
            msg = "cooldown/unavailable windows must be >= 0"
            raise ValueError(msg)
        self._clock = clock
        self._default_cooldown_ms = default_cooldown_ms
        self._default_unavailable_ms = default_unavailable_ms
        self._records: dict[tuple[UUID, UUID], _Record] = {}

    # -- reads ---------------------------------------------------------------------

    def eligibility(
        self, provider_id: UUID, model_id: UUID, *, limits: Mapping[str, object] | None = None
    ) -> Eligibility:
        """O(1) eligibility answer; ``limits`` is the binding's declared metadata."""
        record = self._records.get((provider_id, model_id))
        now = self._clock()
        rpm_limit = _declared_rpm(limits)
        if record is None:
            return Eligibility(eligible=True)
        if record.unavailable_until is not None:
            if now < record.unavailable_until:
                return Eligibility(
                    eligible=False,
                    reason=f"provider unavailable ({_name(record.last_category)})",
                    retry_after_ms=_ms_until(now, record.unavailable_until),
                )
            record.unavailable_until = None
        if record.cooldown_until is not None:
            if now < record.cooldown_until:
                return Eligibility(
                    eligible=False,
                    reason=f"cooldown ({_name(record.last_category)})",
                    retry_after_ms=_ms_until(now, record.cooldown_until),
                )
            record.cooldown_until = None
        if rpm_limit is not None:
            self._roll_window(record, now)
            if record.rpm_used >= rpm_limit:
                assert record.window_start is not None
                window_end = record.window_start + timedelta(seconds=RPM_WINDOW_SECONDS)
                return Eligibility(
                    eligible=False,
                    reason=f"rpm budget exhausted ({record.rpm_used}/{rpm_limit})",
                    retry_after_ms=_ms_until(now, window_end),
                )
        return Eligibility(eligible=True)

    def snapshot(self) -> list[JsonObject]:
        """Read-model rows (normalized vocabulary only) for admin/system views."""
        now = self._clock()
        rows: list[JsonObject] = []
        for (provider_id, model_id), record in sorted(
            self._records.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
        ):
            state = "available"
            reason: str | None = None
            until: datetime | None = None
            if record.unavailable_until is not None and now < record.unavailable_until:
                state, reason, until = (
                    "unavailable",
                    _name(record.last_category),
                    record.unavailable_until,
                )
            elif record.cooldown_until is not None and now < record.cooldown_until:
                state, reason, until = (
                    "cooldown",
                    _name(record.last_category),
                    record.cooldown_until,
                )
            elif record.rpm_limit is not None and record.rpm_used >= record.rpm_limit:
                state, reason = "limited", "rpm"
            rows.append(
                {
                    "provider_id": str(provider_id),
                    "model_id": str(model_id),
                    "state": state,
                    "reason": reason,
                    "cooldown_until": until.isoformat() if until is not None else None,
                    "rpm_used": record.rpm_used,
                    "rpm_limit": record.rpm_limit,
                    "last_category": _name(record.last_category),
                }
            )
        return rows

    # -- writes (called by the execution service after every attempt) ----------------

    def record_attempt(
        self, *, provider_id: UUID, model_id: UUID, limits: Mapping[str, object] | None = None
    ) -> None:
        """Count one request against the RPM window (declared limits only)."""
        record = self._records.setdefault((provider_id, model_id), _Record())
        record.rpm_limit = _declared_rpm(limits)
        self._roll_window(record, self._clock())
        record.rpm_used += 1

    def record_success(self, *, provider_id: UUID, model_id: UUID) -> None:
        record = self._records.get((provider_id, model_id))
        if record is None:
            return
        record.cooldown_until = None
        record.unavailable_until = None
        record.last_category = None

    def record_error(self, *, provider_id: UUID, model_id: UUID, error: ProviderError) -> None:
        """Fold ONE normalized error into the resource's signal (category-driven)."""
        now = self._clock()
        if error.category in _COOLDOWN_CATEGORIES:
            wait_ms = (
                error.retry_after_ms
                if error.retry_after_ms is not None
                else self._default_cooldown_ms
            )
            record = self._records.setdefault((provider_id, model_id), _Record())
            record.cooldown_until = now + timedelta(milliseconds=wait_ms)
            record.last_category = error.category
        elif error.category in _UNAVAILABLE_CATEGORIES:
            record = self._records.setdefault((provider_id, model_id), _Record())
            record.unavailable_until = now + timedelta(milliseconds=self._default_unavailable_ms)
            record.last_category = error.category
        # every other category carries no capacity/availability signal.

    # -- internals ---------------------------------------------------------------------

    @staticmethod
    def _roll_window(record: _Record, now: datetime) -> None:
        if record.window_start is None or now - record.window_start >= timedelta(
            seconds=RPM_WINDOW_SECONDS
        ):
            record.window_start = now
            record.rpm_used = 0


def _declared_rpm(limits: Mapping[str, object] | None) -> int | None:
    """Provider-declared RPM from binding metadata; anything else ⇒ undeclared."""
    if not limits:
        return None
    raw = limits.get("rpm")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        return None
    return raw


def _ms_until(now: datetime, when: datetime) -> int:
    return max(int((when - now).total_seconds() * 1000), 0)


def _name(category: ProviderErrorCategory | None) -> str | None:
    return None if category is None else category.value
