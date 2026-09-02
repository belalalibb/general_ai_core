"""Learning observability — Vision V7 chunk 5 (frozen clause).

The frozen definition: "Learning observability ('what changed since last
review' with evidence)". Recorded derivations:

- WHAT "LEARNING" HONESTLY MEANS HERE (R049 boundary (a), 41 §49): the
  platform has learning GATES (22 §9/§11 condition sets as data) but NO
  training machinery — the LearningDashboard placeholder already states
  this structurally. So observability surfaces what the platform DOES
  change through: admin config lifecycle (21 §8 audited publishes/
  rollbacks), audit events (20 §9 closed set), evaluation records
  (22 §6 verdict rows), and the saved-scenario regression posture (the
  ``regression_pass`` signal the PromotionGate consumes). Fabricating
  accuracy/coverage numbers is forbidden; the report carries ONLY facts
  read from stores, each with evidence rows.
- "LAST REVIEW" is an explicit admin ACT, not an inferred timestamp: an
  admin marks a review; the report answers "what changed since that
  marker". No marker yet = the honest answer "never reviewed" with the
  full history as the delta (deny-by-default would hide changes — the
  OPPOSITE of observability; recorded decision: unreviewed shows
  everything, loudly).
- The marker store is tenant-scoped, in-process, append-only in spirit
  (marking again REPLACES the marker but the act itself is auditable by
  the caller through the returned previous marker — the report is the
  audit trail consumer here, not producer). Same in-process posture as
  ScenarioService (a durable binding is a later, conscious slice).
- EVIDENCE: every count in the report is accompanied by the rows it was
  counted from (bounded by ``evidence_limit`` — newest first), so the
  admin can verify each number (21 §7 evidence posture; 11 §14 nothing
  summarized without the data that backs it).
- GATE TRUTH: the report restates the closed 22 §9/§11 condition sets
  as DATA (from core.learning) and the structural placeholder truth —
  the reader always sees that no training machinery exists (P6).
- CONSUMERS (P3): admin routes + agent tools dispatch through THIS
  service — one store, two consumers. Reading the report is R0;
  MARKING a review is a state change → R1 (recorded: it is a bounded,
  reversible test/ops act, not a config change — R2 is the admin
  config lifecycle's tier).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from core.admin.service import AdminConfigService
from core.audit.ports import AuditLogPort
from core.contracts.base import JsonObject, utc_now
from core.learning import PROMOTION_CONDITIONS, TRAINING_ELIGIBILITY_CONDITIONS

#: Evidence rows per section — bounded so the report stays a report
#: (the full stores remain readable through their own routes).
DEFAULT_EVIDENCE_LIMIT = 20


@dataclass
class _Marker:
    """One tenant's review marker — who marked, and when."""

    reviewed_at: datetime
    reviewed_by: UUID


@dataclass
class LearningObservabilityService:
    """'What changed since last review' over the EXISTING stores (P1).

    Optional seams degrade honestly: an absent store yields a section
    that SAYS it is absent (``available: False``) — never silently
    empty, never fabricated (P6).
    """

    audit: AuditLogPort | None = None
    admin_service: AdminConfigService | None = None
    evidence_limit: int = DEFAULT_EVIDENCE_LIMIT
    _markers: dict[UUID, _Marker] = field(default_factory=dict)

    def mark_reviewed(self, tenant_id: UUID, actor_id: UUID) -> JsonObject:
        """Record the review act; returns the new AND previous marker.

        The previous marker rides back so the act is self-evidencing —
        the caller sees exactly which window was closed.
        """
        previous = self._markers.get(tenant_id)
        marker = _Marker(reviewed_at=utc_now(), reviewed_by=actor_id)
        self._markers[tenant_id] = marker
        return {
            "reviewed_at": marker.reviewed_at.isoformat(),
            "reviewed_by": str(actor_id),
            "previous": (
                None
                if previous is None
                else {
                    "reviewed_at": previous.reviewed_at.isoformat(),
                    "reviewed_by": str(previous.reviewed_by),
                }
            ),
        }

    def changes_since_review(self, tenant_id: UUID) -> JsonObject:
        """The report: every change window fact WITH its evidence rows."""
        marker = self._markers.get(tenant_id)
        since = marker.reviewed_at if marker is not None else None

        report: JsonObject = {
            # No marker = never reviewed = the FULL history is the delta,
            # said out loud (recorded decision — hiding would defeat
            # observability).
            "reviewed": marker is not None,
            "since": since.isoformat() if since is not None else None,
            "audit": self._audit_section(tenant_id, since),
            "config_changes": self._config_section(tenant_id, since),
            "regression_posture": self._regression_posture(),
            # The structural truth, restated: gates exist as condition
            # DATA; training machinery does not (R049 (a), 41 §49).
            "learning_machinery": {
                "placeholder": True,
                "training_eligibility_conditions": list(TRAINING_ELIGIBILITY_CONDITIONS),
                "promotion_conditions": list(PROMOTION_CONDITIONS),
            },
        }
        return report

    # --- sections (each honest about absence) -----------------------------------

    def _audit_section(self, tenant_id: UUID, since: datetime | None) -> JsonObject:
        if self.audit is None:
            return {"available": False}
        events = self.audit.read(tenant_id)
        window = [e for e in events if since is None or e.occurred_at > since]
        by_type: dict[str, int] = {}
        for event in window:
            by_type[event.event_type.value] = by_type.get(event.event_type.value, 0) + 1
        # Newest-first evidence, bounded; counts cover the WHOLE window.
        evidence = [
            e.model_dump(mode="json", exclude_none=True)
            for e in reversed(window[-self.evidence_limit :])
        ]
        return {
            "available": True,
            "events_in_window": len(window),
            "by_type": dict(sorted(by_type.items())),
            "evidence": evidence,
            "evidence_truncated": len(window) > self.evidence_limit,
        }

    def _config_section(self, tenant_id: UUID, since: datetime | None) -> JsonObject:
        if self.admin_service is None:
            return {"available": False}
        changes = self.admin_service.list_changes(tenant_id)
        window = [c for c in changes if since is None or c.created_at > since]
        by_state: dict[str, int] = {}
        for change in window:
            by_state[change.state.value] = by_state.get(change.state.value, 0) + 1
        newest_first = sorted(window, key=lambda c: c.created_at, reverse=True)
        evidence = [
            c.model_dump(mode="json", exclude_none=True)
            for c in newest_first[: self.evidence_limit]
        ]
        return {
            "available": True,
            "changes_in_window": len(window),
            "by_state": dict(sorted(by_state.items())),
            "evidence": evidence,
            "evidence_truncated": len(window) > self.evidence_limit,
        }

    def _regression_posture(self) -> JsonObject:
        """The PromotionGate's ``regression_pass`` input, as posture DATA.

        The report does NOT run the regression pack (running is the
        Regression Center's R1 act; a report is R0 and must stay pure
        read) — it names where the signal comes from so the reviewer
        knows what to run. Recorded decision: observability points at
        evidence sources, it never silently triggers executions.
        """
        return {
            "signal": "regression_pass",
            "consumed_by": "PromotionGate (22 §11)",
            "produced_by": "POST /v1/admin/scenarios/regression-pack",
            "note": (
                "Run the regression pack to refresh this signal; the report "
                "never triggers executions."
            ),
        }
