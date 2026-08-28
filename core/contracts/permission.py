"""Permission contract — the platform permission catalog entity.

Contract authority (FINAL Phase 3 gap-fix: 41 §6 lists ``permissions`` as
a Postgres source-of-truth entity; 03's inventory has no Permission entity
— derivation recorded below, never hidden):

- docs/ai_orchestration_pack/final_docs_v3/20_SECURITY_THREAT_MODEL.md §4
  (the firewall decision input ``permission`` is a dotted identifier,
  e.g. ``github.pr.create``; :data:`core.contracts.security.PermissionKey`
  already names that string shape — reused here, not duplicated).
- final_docs_v3/14_SKILLS_AND_TOOLS.md §8 (the GitHub permission catalog
  — the concrete list this entity stores rows of) and the rule verbatim:
  "Default write operations require approval".
- final_docs_v3/14 §4 tool-manifest ``approval`` values — the closed
  :class:`core.contracts.tools.ApprovalRequirement` set (reused, not
  duplicated).

Field derivation note (explicit, no invention hidden): the specs define
the permission as an IDENTIFIER plus an approval posture — nothing more.
The entity is therefore minimal: ``id`` (storage anchor), ``key`` (the
20 §4 dotted identifier, the unique lookup key), ``approval`` (the
14 §4/§8 requirement). No description/status/grouping fields exist in any
spec, so none are invented (41 §31 scope control).

Catalog posture: permissions are a PLATFORM catalog (the 20 §4 note in
``core/contracts/security.py`` records "the catalogs are
admin-configurable, not contract-closed") — deliberately NOT
tenant-scoped; grants/denials per tenant are firewall policy DATA, not
catalog rows.

Deny-by-default (41 §1 rule 9), encoded in DATA: ``approval`` defaults to
``ALWAYS`` — the most restrictive requirement. A permission row that does
not explicitly relax its approval posture requires approval every time.
This matches the tool-manifest posture (a declared permission absent from
``approval_policy`` resolves to ALWAYS) and the 14 §8 rule that write
operations require approval by default.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.base import ContractModel
from core.contracts.security import PermissionKey
from core.contracts.tools import ApprovalRequirement


class Permission(ContractModel):
    """Permission catalog entry (41 §6 ``permissions``; shape from 20 §4 + 14 §8)."""

    id: UUID
    key: PermissionKey
    approval: ApprovalRequirement = ApprovalRequirement.ALWAYS
