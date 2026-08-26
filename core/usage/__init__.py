"""Usage accounting — task-unit reserve/settle (MVP Phase 5, 41 §43/§44).

Public surface: the usage-accounting port, its errors, and the in-memory
binding. Durable billing/persistence bindings arrive in ``infrastructure/``
later behind the same port; no real payments integration in the MVP
(41 §43 scope: "units estimate/reserve/settle").
"""

from core.usage.errors import (
    BudgetExceeded,
    EntitlementNotConfigured,
    ReservationAlreadyResolved,
    ReservationNotFound,
    UsageError,
)
from core.usage.memory import InMemoryUsageAccounting
from core.usage.ports import UsageAccountingPort

__all__ = [
    "BudgetExceeded",
    "EntitlementNotConfigured",
    "InMemoryUsageAccounting",
    "ReservationAlreadyResolved",
    "ReservationNotFound",
    "UsageAccountingPort",
    "UsageError",
]
