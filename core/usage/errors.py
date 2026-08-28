"""Usage-accounting boundary errors (T-IMPL-024; 03 §7; 10 §8/§9; 21 §5).

Two distinct failure families (deliberate):

- ENTITLEMENT denials (:class:`EntitlementNotConfigured`,
  :class:`BudgetExceeded`) are legitimate runtime outcomes raised BEFORE any
  provider work starts — the API maps them to the unified
  ``entitlement_exceeded`` code (10 §9). Deny-by-default is explicit here:
  a tenant with NO configured budget is DENIED loudly, never granted an
  implicit allowance (20 §4 posture applied to billing data).
- LEDGER faults (:class:`ReservationNotFound`,
  :class:`ReservationAlreadyResolved`) are accounting bugs — settling or
  refunding a reservation that does not exist or was already resolved would
  corrupt the ledger, so they raise immediately and are never absorbed.
"""

from __future__ import annotations

from uuid import UUID


class UsageError(Exception):
    """Base class for usage-accounting failures."""


class EntitlementNotConfigured(UsageError):
    """No task-unit budget is configured for the tenant.

    Deny-by-default (explicit decision, not an accident): absence of
    entitlement data means DENY — the service never invents a default
    allowance for an unknown tenant (20 §4; 21 §5 plans are the only
    source of limits).
    """

    def __init__(self, tenant_id: UUID) -> None:
        super().__init__(f"no task-unit budget configured for tenant {tenant_id}")
        self.tenant_id = tenant_id


class BudgetExceeded(UsageError):
    """The reservation would exceed the tenant's remaining task units.

    Carries the accounting facts so the API can explain the denial
    (10 §9 ``entitlement_exceeded``) without exposing other tenants' data.
    """

    def __init__(
        self, tenant_id: UUID, *, requested: float, remaining: float
    ) -> None:
        super().__init__(
            f"tenant {tenant_id} has {remaining} task units remaining; "
            f"reservation of {requested} denied"
        )
        self.tenant_id = tenant_id
        self.requested = requested
        self.remaining = remaining


class UnknownComplexity(UsageError):
    """No unit value is configured for the task's complexity (41 §19).

    Deny-by-default applied to pricing: a complexity absent from the
    configuration-driven unit table has NO price — inventing one would
    fabricate billing policy, so estimation refuses loudly instead.
    """

    def __init__(self, complexity: str, *, known: list[str]) -> None:
        super().__init__(
            f"no task-unit value configured for complexity {complexity!r}; "
            f"known: {known}"
        )
        self.complexity = complexity
        self.known = known


class ReservationNotFound(UsageError):
    """No ledger entry exists for the execution being settled/refunded."""

    def __init__(self, execution_id: UUID) -> None:
        super().__init__(f"no usage reservation for execution {execution_id}")
        self.execution_id = execution_id


class ReservationAlreadyResolved(UsageError):
    """The ledger entry was already settled/refunded/failed — resolution is final.

    A reservation resolves exactly once (03 §7 lifecycle); double settlement
    would double-charge and is therefore a loud accounting fault.
    """

    def __init__(self, execution_id: UUID, status: str) -> None:
        super().__init__(
            f"usage reservation for execution {execution_id} already resolved "
            f"(status={status})"
        )
        self.execution_id = execution_id
        self.status = status
