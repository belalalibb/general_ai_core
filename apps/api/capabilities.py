"""Capability Catalog — Vision V7 chunk 1 (frozen-roadmap clause).

The frozen definition: "Capability Catalog (honest closed-set
Available/Inert/Unavailable)". Recorded derivations:

- HONESTY SOURCE: the ONLY place that knows which seams are actually
  composed is ``create_app`` at composition time — so the catalog is
  DERIVED there from the same variables that mount (or don't mount) each
  route/service, never from documentation claims (41 §49: nothing is
  claimed Available that a request cannot actually reach).
- CLOSED SETS both ways: ``CapabilityState`` is a closed 3-value StrEnum
  (the frozen wording verbatim) and ``CAPABILITY_IDS`` is a closed
  frozenset — an entry with an unknown id or state cannot be constructed
  (extra ids are a construction-time ValueError, not silent data).
- STATE MEANINGS (recorded):
  * AVAILABLE   — the seam is composed; a request can exercise it NOW in
                  this process.
  * INERT       — the machinery exists in the repository (proven by the
                  capability's ``evidence``) but the seam was NOT composed
                  into this app instance; wiring, not building, activates
                  it. This is the honest label for "code exists, route
                  absent" (20 §4 absent-seam posture).
  * UNAVAILABLE — requires work that does not exist in the repo yet
                  (e.g. inline token streaming needs streaming provider
                  adapters — recorded at V6-2). Never used for merely
                  un-wired machinery.
- PROCESS SCOPE: like the SYS-1 system read-model, the catalog reports
  THIS process's composition only — it cannot claim fleet truths. The
  serialized form carries ``scope: process`` unconditionally.
- CONSUMERS (P3): the admin route (apps/api/admin.py) and the admin
  agent's R0 tool both render ``catalog_json`` — one derivation, two
  consumers, zero parallel state.

This module is PURE data + derivation helpers: no I/O, no FastAPI
dependency, importable by both consumers without import-order issues.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.admin.service import field_rules_json
from core.contracts.admin import ACTION_AREA, FINAL_ACTIVE_ADMIN_AREAS, AdminAction, AdminArea
from core.contracts.base import JsonObject


class CapabilityState(StrEnum):
    """The frozen-roadmap closed set, verbatim."""

    AVAILABLE = "available"
    INERT = "inert"
    UNAVAILABLE = "unavailable"


#: The closed capability id set (V7 chunk 1). Ids name PLATFORM
#: capabilities a composition root decides about — one row per create_app
#: seam family plus the recorded UNAVAILABLE items. Extending this set is
#: a deliberate edit HERE (closed by test), never ad-hoc strings.
CAPABILITY_IDS: frozenset[str] = frozenset(
    {
        "execute.sync",
        "execute.async",
        "execute.token_streaming",
        "executions.progress_sse",
        "conversations.persistence",
        "context.composition",
        "models.listing",
        "skills.listing",
        "usage.reporting",
        "webhooks.registration",
        "webhooks.delivery_staging",
        "admin.control_plane",
        "learning.lifecycle",
        "rate_limits.execute",
        "auth.sessions",
        "health.liveness",
        # R172 C7: dev seam (create_app(dev_bindings=)) -> /v1/dev publish-modes.
        "dev.publish_modes",
        # R177-FIX-02: mounted-but-uncatalogued surfaces (A04) get honest rows.
        "agent.runtime",  # create_app(agent=) -> /v1/agent-tools + strategy=agent
        "sourcechange.workflow",  # admin seam -> /v1/admin/source-changes/* (R3, applier=None)
        "skills.import",  # create_app(skills_import=True) when the console attaches SKL-1
        "workspaces.projects",  # always mounted -> /v1/workspaces + /v1/projects
        "evaluation.records",  # admin seam -> /v1/admin/evaluations/* reads
        # R179 4.2: the ONE authorized closed-set widening (22 -> 23). Durable
        # custody governance routes (R178 DEC03) are mounted ONLY when a
        # LearningCustodyPort is composed AND the admin surface carries an
        # audit log — an operator surface that existed without a shelf row.
        # -> /v1/admin/learning/custody/{revoke,sweep,release-legacy-hold}
        "learning.custody_governance",
    }
)


@dataclass(frozen=True)
class Capability:
    """One catalog row — id, honest state, and the evidence pointer."""

    id: str
    state: CapabilityState
    evidence: str  # the module/route/seam that proves the state claim

    def __post_init__(self) -> None:
        if self.id not in CAPABILITY_IDS:
            raise ValueError(f"unknown capability id {self.id!r}; the catalog id set is closed")


def catalog_json(entries: tuple[Capability, ...]) -> JsonObject:
    """Serialize a derived catalog — the shape BOTH consumers render.

    Refuses duplicates and requires exactly the full closed set: a
    composition root cannot silently omit a capability (an omitted row
    would be a hidden claim).
    """
    seen = {entry.id for entry in entries}
    if len(seen) != len(entries):
        raise ValueError("duplicate capability ids in catalog derivation")
    missing = CAPABILITY_IDS - seen
    if missing:
        raise ValueError(f"catalog derivation incomplete; missing: {sorted(missing)}")
    return {
        "scope": "process",  # SYS-1 posture: this process only, forced label
        "capabilities": [
            {
                "id": entry.id,
                "state": entry.state.value,
                "evidence": entry.evidence,
            }
            for entry in sorted(entries, key=lambda e: e.id)
        ],
    }


#: The shelf row that owns the admin change lifecycle (the ONLY capability
#: whose "supported actions" question has a canonical answer today).
ADMIN_ACTIONS_CAPABILITY_ID = "admin.control_plane"


def admin_actions_json() -> JsonObject:
    """R179 4.3 — action discovery, DERIVED from the canonical vocabulary.

    A generic consumer asks "which admin actions does the control plane
    support, and which area owns each?" and gets a pure function of
    ``core.contracts.admin.ACTION_AREA`` (one owner per action, closed) and
    ``FINAL_ACTIVE_ADMIN_AREAS``. There is NO second list to maintain: every
    ``AdminAction`` and every ``AdminArea`` value is enumerated from the enums,
    so drift between vocabulary and discovery is impossible by construction.

    R179 rulings Q4 (DEC-A approved): the payload half is now the SAME
    declared table the validator reads — ``core.admin.service.PAYLOAD_FIELD_RULES``
    — projected per action as ``fields`` (name / kind / required / contract).
    A form built from a row and the refusal the validator answers are two
    reads of one source; no second list exists. The shelf row shape
    ``{id,state,evidence}`` is untouched — this is a separate read model on
    its own route.
    """
    actions = [
        {
            "action": action.value,
            "area": ACTION_AREA[action].value,
            "fields": field_rules_json(action),
        }
        for action in sorted(AdminAction, key=lambda a: a.value)
    ]
    areas = [
        {
            "area": area.value,
            "active": area in FINAL_ACTIVE_ADMIN_AREAS,
            "actions": sorted(a.value for a, owner in ACTION_AREA.items() if owner is area),
        }
        for area in sorted(AdminArea, key=lambda a: a.value)
    ]
    return {
        "scope": "process",
        "capability": ADMIN_ACTIONS_CAPABILITY_ID,
        "vocabulary": "core.contracts.admin.ACTION_AREA",
        "field_rules": "core.admin.service.PAYLOAD_FIELD_RULES",
        "actions": actions,
        "areas": areas,
    }
