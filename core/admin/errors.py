"""Admin control-plane errors (closed, minimal set for the MVP service).

Anti-enumeration posture carried from core/storage, core/memory and
core/evaluation (20 §6): a config change that is absent and one owned by
ANOTHER tenant raise the SAME NotFound error.
"""

from __future__ import annotations


class AdminError(Exception):
    """Base class for admin control-plane failures."""


class InactiveAdminArea(AdminError):
    """The named admin area is representable but has no MVP actions.

    R049-pattern boundary (mirroring ``InactiveGraderType``): only
    ``MVP_ACTIVE_ADMIN_AREAS`` accept changes in MVP Phase 7 (41 §46
    "admin models/providers/plans/routing"). Naming any other 21 §2 area
    is denied LOUDLY at draft time — a silent no-op would fake an admin
    surface that does not exist yet.
    """

    def __init__(self, area: object) -> None:
        super().__init__(f"admin area not active in MVP Phase 7: {area}")


class ChangeNotFound(AdminError):
    """No config change with this id within the caller's tenant scope.

    Deliberately also raised for changes owned by ANOTHER tenant
    (anti-enumeration, 20 §6).
    """

    def __init__(self, change_id: object) -> None:
        super().__init__(f"config change not found: {change_id}")


class InvalidLifecycleTransition(AdminError):
    """The 21 §3 lifecycle order was violated (e.g. publish before preview).

    The lifecycle is Draft -> Validate -> Preview Impact -> Publish ->
    Rollback; every step requires the exact preceding state. REJECTED is
    terminal.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"invalid lifecycle transition: {detail}")


class RollbackUnavailable(AdminError):
    """No previous state was captured, so rollback would have to invent one.

    Honesty rule: rollback RESTORES a recorded prior state (21 §8
    "rollback target"); when none exists (e.g. the first plan configuration
    for a tenant) the service denies loudly instead of fabricating a
    "previous version" that never was.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"rollback unavailable: {detail}")
