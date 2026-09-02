"""Self-Review + Change Impact Simulator — Vision V7 chunk 6 (frozen clause).

The frozen definition: "Self-Review + Change Impact Simulator
(evidence-backed proposals, never auto-apply)". Recorded derivations:

- SELF-REVIEW is ASSEMBLY, not judgment: the platform reviews itself by
  composing the evidence surfaces that ALREADY exist (P1) — the
  capability catalog (chunk 1: honest closed-set states with evidence
  pointers), the config-change lifecycle (21 §3 states by count with
  the newest records), the saved-scenario posture (chunk 3: what is
  replayable and against which checks), and the review state (chunk 5:
  reviewed-or-not + marker). No new judgment machinery, no scores, no
  fabricated health metrics (41 §49) — each section is facts + where
  they came from. Absent seams answer ``available: False`` (P6).
- THE SIMULATOR **IS** THE EXISTING LIFECYCLE: ``propose_change`` runs
  draft → validate → preview through the SAME AdminConfigService the
  admin routes drive — never a parallel simulation of what a change
  "would" do (the lifecycle's own ``validation_result`` and
  ``impact_preview`` ARE the evidence). A proposal therefore ends in
  exactly one of two honest states:
    * REJECTED — validation refused, reason attached (terminal); or
    * VALIDATED + impact_preview attached — ready for a HUMAN to
      publish through the existing route.
- "NEVER AUTO-APPLY", structurally: this module never calls
  ``publish``. Publishing remains the explicit admin act on the
  existing lifecycle route (21 §8 audited), and the proposal SAYS so
  (``apply`` section naming the route). Tests pin that no proposal
  ever reaches PUBLISHED and no ADMIN_CONFIG_PUBLISHED audit row is
  produced by proposing.
- CONSUMERS (P3): admin routes + agent tools dispatch through THIS
  service. ``self_review`` is R0 (pure read). ``propose_change`` is R2
  (it creates config-lifecycle state — the SAME tier as the existing
  draft/validate/preview agent tools; a proposal is exactly those three
  acts composed).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apps.api.capabilities import Capability
from apps.api.learning_observability import LearningObservabilityService
from apps.api.scenarios import ScenarioService, scenario_json
from core.admin.service import AdminConfigService
from core.contracts.admin import AdminAction, ConfigChange, ConfigLifecycleState
from core.contracts.base import JsonObject

#: Newest lifecycle records carried as self-review evidence (bounded —
#: the full list stays readable through GET /v1/admin/changes).
CHANGE_EVIDENCE_LIMIT = 10


def _change_json(change: ConfigChange) -> JsonObject:
    return change.model_dump(mode="json", exclude_none=True)


@dataclass(frozen=True)
class SelfReviewService:
    """Evidence assembly + lifecycle-composed proposals (module header).

    Every seam is the SAME instance the corresponding admin surface
    serves (composition-root agreement) — one derivation, N consumers.
    """

    admin_service: AdminConfigService | None = None
    catalog: tuple[Capability, ...] = ()
    scenarios: ScenarioService | None = None
    observability: LearningObservabilityService | None = None

    # --- Self-Review (R0: pure read over existing surfaces) --------------------

    def self_review(self, tenant_id: UUID) -> JsonObject:
        """The platform's honest self-portrait — facts + provenance only."""
        return {
            "capabilities": self._capability_section(),
            "config_lifecycle": self._lifecycle_section(tenant_id),
            "scenarios": self._scenario_section(tenant_id),
            "review_state": self._review_section(tenant_id),
            # The posture, restated where the reader is (P6): this report
            # proposes nothing and applies nothing.
            "posture": {
                "proposals": "POST /v1/admin/changes/propose",
                "apply": "human publish via POST /v1/admin/changes/{id}/publish",
                "auto_apply": "never",
            },
        }

    def _capability_section(self) -> JsonObject:
        if not self.catalog:
            return {"available": False}
        by_state: dict[str, int] = {}
        for entry in self.catalog:
            by_state[entry.state.value] = by_state.get(entry.state.value, 0) + 1
        return {
            "available": True,
            "by_state": dict(sorted(by_state.items())),
            # Every row carries its own evidence pointer (chunk 1 shape).
            "rows": [
                {"id": e.id, "state": e.state.value, "evidence": e.evidence}
                for e in sorted(self.catalog, key=lambda e: e.id)
            ],
        }

    def _lifecycle_section(self, tenant_id: UUID) -> JsonObject:
        if self.admin_service is None:
            return {"available": False}
        changes = self.admin_service.list_changes(tenant_id)
        by_state: dict[str, int] = {}
        for change in changes:
            by_state[change.state.value] = by_state.get(change.state.value, 0) + 1
        newest_first = sorted(changes, key=lambda c: c.created_at, reverse=True)
        return {
            "available": True,
            "total": len(changes),
            "by_state": dict(sorted(by_state.items())),
            "evidence": [_change_json(c) for c in newest_first[:CHANGE_EVIDENCE_LIMIT]],
            "evidence_truncated": len(changes) > CHANGE_EVIDENCE_LIMIT,
        }

    def _scenario_section(self, tenant_id: UUID) -> JsonObject:
        if self.scenarios is None:
            return {"available": False}
        rows = self.scenarios.list(tenant_id)
        return {
            "available": True,
            "saved": len(rows),
            "rows": [scenario_json(s) for s in rows],
            # A report never runs anything (chunk 5 recorded posture) —
            # it points at the act that would produce fresh verdicts.
            "refresh_via": "POST /v1/admin/scenarios/regression-pack",
        }

    def _review_section(self, tenant_id: UUID) -> JsonObject:
        if self.observability is None:
            return {"available": False}
        report = self.observability.changes_since_review(tenant_id)
        # Only the review STATE rides here; the full windowed report is
        # its own surface (no duplicated rendering).
        return {
            "available": True,
            "reviewed": report["reviewed"],
            "since": report["since"],
            "full_report": "GET /v1/admin/learning/changes-since-review",
        }

    # --- Change Impact Simulator (R2: composes the EXISTING lifecycle) ---------

    def propose_change(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        action: AdminAction,
        payload: JsonObject,
    ) -> JsonObject:
        """draft → validate → preview through the REAL lifecycle; NEVER publish.

        Raises the lifecycle's own errors (InactiveAdminArea) for the
        caller to map — a proposal against a non-existent area is the
        request's fault, not a proposal outcome. Validation REFUSAL,
        however, IS a proposal outcome (honest rejected proposal).
        """
        if self.admin_service is None:
            raise RuntimeError(
                "propose_change requires the admin lifecycle seam"
            )  # composition error, not a request error — loud (11 §14)
        drafted = self.admin_service.draft(
            tenant_id=tenant_id,
            actor_id=actor_id,
            action=action,
            payload=dict(payload),
        )
        validated = self.admin_service.validate(tenant_id, drafted.id)
        if validated.state is ConfigLifecycleState.REJECTED:
            # An honest rejected proposal: the lifecycle's own named
            # reason IS the evidence (terminal — nothing to publish).
            return {
                "proposed": True,
                "outcome": "rejected",
                "change": _change_json(validated),
                "evidence": {"validation_result": validated.validation_result},
            }
        previewed = self.admin_service.preview(tenant_id, validated.id)
        return {
            "proposed": True,
            "outcome": "ready_for_review",
            "change": _change_json(previewed),
            # The lifecycle's OWN artifacts are the proposal's evidence
            # (module header: never a parallel simulation).
            "evidence": {
                "validation_result": previewed.validation_result,
                "impact_preview": previewed.impact_preview,
            },
            # Never auto-apply — said where the reader is, with the one
            # legitimate path to application (a HUMAN act).
            "apply": {
                "auto_apply": "never",
                "human_route": f"POST /v1/admin/changes/{previewed.id}/publish",
            },
        }
