"""Context Validation Lab — Vision V7 chunk 4 (frozen clause).

The frozen definition: "Context Validation Lab (workspace + async +
core/evaluation verdicts)". Recorded derivations:

- The lab is a DRY-RUN surface over the REAL ContextComposer (P1) — it
  composes exactly what an execute request would compose (same composer
  instance, same memory/history/role stores) and returns the blocks,
  the named exclusions, and closed lab verdicts WITHOUT executing
  anything. Composition reads stores and writes nothing — the lab is a
  pure read surface (its agent tools are R0, unlike scenario replay's
  R1).
- LAB CHECKS are a CLOSED name set derived from the 13 §5/§10 truths
  the composer already promises: the ask block is present and last
  (recorded deterministic order), the context budget is respected
  (13 §10 "context budget respected"), composition is deterministic
  (13 §5 "the same inputs always compose the same context" — proven by
  composing TWICE and comparing), and every exclusion carries a
  closed-set reason (11 §14 explainability). Verdicts are DATA over the
  actual composition — no new grader machinery (the core/evaluation
  DeterministicCheck posture: named, pure, cheap; its dataclass binds
  to execution output, so the lab records its own name tuple rather
  than misusing that contract).
- HONEST FAILURES (P6): an impossible budget or a refused role is a
  ``validated: False`` result carrying the named facts (required/budget,
  the registry's own denial wording) — the lab reports reality, it
  never fabricates a composition.
- 13 §7 OWNERSHIP: a conversation_id is admitted through
  ``get_conversation`` BEFORE composing; absent, foreign-tenant and
  foreign-user ids all answer identically (recorded decision: stricter
  than the execute path's named same-tenant 401 — the lab is an admin
  read surface, enumeration through it must yield nothing, 20 §6).
- SEAM: the lab exists ONLY when a composer is composed (no composer =
  nothing to validate = absent routes/tools, 20 §4 deny-by-default).
- CONSUMERS (P3): admin routes and the agent's tools both dispatch
  through THIS service — one composer, two consumers, zero parallel
  composition logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from pydantic import Field

from core.context.composer import ContextComposer
from core.context.errors import ContextBudgetExceeded
from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.contracts.context import (
    ComposedContext,
    ContextBlockType,
    ContextComposeRequest,
    ContextExclusionReason,
)
from core.memory.errors import ConversationNotFound
from core.memory.ports import ConversationStorePort
from core.roles.errors import RoleNotRegistered, RoleNotSelectable

#: The CLOSED lab-check name set — each name is a 13 §5/§10 composer
#: promise the lab verifies over the ACTUAL composition. Extending means
#: a new recorded composer truth, never an ad-hoc string.
LAB_CHECK_NAMES: tuple[str, ...] = (
    "ask_block_present",
    "budget_respected",
    "deterministic_composition",
    "exclusions_named",
)

#: One answer for absent, foreign-tenant AND foreign-user conversation
#: ids (20 §6 — recorded decision, see module docstring).
_UNKNOWN_CONVERSATION = "unknown conversation id"


class ContextLabRequest(ContractModel):
    """POST /v1/admin/context-lab/validate body — the dry-run inputs.

    Mirrors ContextComposeRequest minus the identity fields: tenant and
    user come from the authenticated principal, never from the client.
    """

    ask: str = Field(min_length=1, max_length=200_000)
    role_id: UUID | None = None
    conversation_id: UUID | None = None
    history_limit: int = Field(default=20, ge=0, le=1_000)
    context_budget: int = Field(default=16_000, ge=1, le=2_000_000)
    allow_high_sensitivity: bool = False
    relevant_keys: list[BoundedStr] | None = None


class ConversationNotAdmitted(KeyError):
    """The lab's conversation admission refused (absent/foreign — same)."""


@dataclass(frozen=True)
class ContextLabService:
    """Dry-run validation over the REAL composer — one instance, shared.

    ``conversations`` is the ownership-admission store (13 §7); when the
    composition root has no conversations seam, a conversation_id is
    refused honestly rather than composed unverified (deny-by-default).
    """

    composer: ContextComposer
    conversations: ConversationStorePort | None = None

    def checks(self) -> list[str]:
        """The closed lab-check name set, sorted — pure data."""
        return sorted(LAB_CHECK_NAMES)

    def validate(
        self, tenant_id: UUID, user_id: UUID, request: ContextLabRequest
    ) -> JsonObject:
        """Compose for real, grade the composition, return verdicts as data.

        Raises ConversationNotAdmitted for absent/foreign conversation ids
        (the route maps it to the recorded 404; the agent tool to an
        honest error string). Every OTHER failure is a ``validated: False``
        result — composition facts are lab data, not transport errors.
        """
        if request.conversation_id is not None:
            self._admit_conversation(tenant_id, user_id, request.conversation_id)

        compose_request = ContextComposeRequest(
            tenant_id=tenant_id,
            user_id=user_id,
            ask=request.ask,
            role_id=request.role_id,
            conversation_id=request.conversation_id,
            history_limit=request.history_limit,
            context_budget=request.context_budget,
            allow_high_sensitivity=request.allow_high_sensitivity,
            relevant_keys=request.relevant_keys,
        )
        try:
            composed = self.composer.compose(compose_request)
            # Determinism is a composer PROMISE (13 §5) — prove it, don't
            # assume it: the same request composes a second time.
            recomposed = self.composer.compose(compose_request)
        except ContextBudgetExceeded as exc:
            return {
                "validated": False,
                "error": "mandatory context exceeds the context budget",
                "required": exc.required,
                "budget": exc.budget,
            }
        except RoleNotRegistered:
            return {"validated": False, "error": "unknown role id"}
        except RoleNotSelectable as exc:
            # The registry's own named denial crosses as data (11 §14).
            return {"validated": False, "error": str(exc)}

        check_rows, passed = self._grade(request, composed, recomposed)
        return {
            "validated": True,
            "passed": passed,
            "checks": check_rows,
            "context": composed.model_dump(mode="json", exclude_none=True),
        }

    # --- internals ------------------------------------------------------------

    def _admit_conversation(
        self, tenant_id: UUID, user_id: UUID, conversation_id: UUID
    ) -> None:
        """13 §7 admission: absent, foreign-tenant, foreign-user — one answer."""
        if self.conversations is None:
            # No conversations seam composed: history cannot be verified as
            # the caller's own, so it is refused, never composed blind.
            raise ConversationNotAdmitted(_UNKNOWN_CONVERSATION)
        try:
            conversation = self.conversations.get_conversation(
                tenant_id, conversation_id
            )
        except ConversationNotFound:
            raise ConversationNotAdmitted(_UNKNOWN_CONVERSATION) from None
        if conversation.user_id != user_id:
            raise ConversationNotAdmitted(_UNKNOWN_CONVERSATION)

    def _grade(
        self,
        request: ContextLabRequest,
        composed: ComposedContext,
        recomposed: ComposedContext,
    ) -> tuple[list[JsonObject], bool]:
        """The closed check set, each verdict over the ACTUAL composition."""
        blocks = composed.context_blocks
        ask_blocks = [b for b in blocks if b.type is ContextBlockType.ASK]
        results: dict[str, bool] = {
            # Recorded deterministic order: the ask composes LAST, once.
            "ask_block_present": (
                len(ask_blocks) == 1 and blocks[-1].type is ContextBlockType.ASK
            ),
            # 13 §10 "context budget respected" — over content characters,
            # the same unit the composer budgets in.
            "budget_respected": (
                sum(len(b.content) for b in blocks) <= request.context_budget
            ),
            # 13 §5 determinism — two real compositions, byte-identical.
            "deterministic_composition": (
                composed.model_dump(mode="json")
                == recomposed.model_dump(mode="json")
            ),
            # 11 §14 — every exclusion names a closed-set reason.
            "exclusions_named": all(
                row.reason in ContextExclusionReason for row in composed.excluded
            ),
        }
        assert set(results) == set(LAB_CHECK_NAMES)  # closed set, total
        check_rows: list[JsonObject] = [
            {"name": name, "passed": results[name]} for name in sorted(results)
        ]
        return check_rows, all(results.values())
