"""Context composer module (MVP Phase 6 slice 3, 41 §45 / 13 §5).

Consumes the EXISTING seams — MemoryStorePort / ConversationStorePort
(T-IMPL-025) and RoleRegistry (T-IMPL-026) — no new storage. Everything
excluded from a composition is named data (11 §14 posture).
"""

from core.context.composer import ContextComposer
from core.context.errors import ContextBudgetExceeded, ContextComposerError

__all__ = [
    "ContextBudgetExceeded",
    "ContextComposer",
    "ContextComposerError",
]
