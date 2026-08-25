"""Authorization / Security contracts — Capability Firewall decision contract.

Contract authority: docs/ai_orchestration_pack/final_docs_v3/20_SECURITY_THREAT_MODEL.md
§4 (Capability Firewall). Carried exactly — decision inputs field-for-field
from the documented JSON example; the decision output set is closed verbatim.

Interpretation notes (documented, not invented):

- ``actor``: the §4 example value is ``"user_or_system"`` — read as the type
  annotation "user or system", so the actor kind is the closed set
  ``user|system``. The LLM is never an authority actor (20 §1: "The LLM is
  untrusted for authority decisions").
- ``approval_state``: the example writes ``"approved|null"`` — closed as
  ``approved`` or absent (None).
- ``risk_level``: only the example value ``"medium"`` appears in the specs;
  no closed enumeration is documented, so it stays an open bounded string.
  Closing it would invent spec.
- ``permission`` / ``entitlement`` / ``resource`` / ``scope``: dotted or
  namespaced identifier strings per the §4 example
  (``github.pr.create`` / ``github_write`` / ``repo:owner/name`` /
  ``project``); carried as bounded strings — the catalogs are
  admin-configurable, not contract-closed.

Deny-by-default posture (20 §3/§4): a firewall decision must be explicit;
there is no implicit-allow value and no default decision.

RBAC/entitlement note: 03 §6 ``Role`` is an *agent prompt role*, not an RBAC
role — no RBAC entity is defined by the specs beyond the permission /
entitlement identifiers used here, so none is invented.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from core.contracts.base import BoundedStr, ContractModel

# --- Identifier aliases (20 §4 example; catalogs are admin-configurable) --------

# e.g. "github.pr.create"
PermissionKey = BoundedStr
# e.g. "github_write"
EntitlementKey = BoundedStr
# e.g. "repo:owner/name"
ResourceRef = BoundedStr
# e.g. "project"
ScopeRef = BoundedStr


# --- Closed sets (20 §4, verbatim) ----------------------------------------------


class ActorKind(StrEnum):
    """Firewall actor kind (20 §4 ``actor: user_or_system``) — closed set.

    The LLM is untrusted for authority decisions (20 §1) and is therefore
    not an actor kind.
    """

    USER = "user"
    SYSTEM = "system"


class FirewallDecision(StrEnum):
    """Capability Firewall decision output (20 §4) — closed set, verbatim."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    ALLOW_WITH_LIMIT = "ALLOW_WITH_LIMIT"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


# --- Decision input (20 §4 "Required decision inputs", field-for-field) ---------


class FirewallDecisionInput(ContractModel):
    """Required decision inputs for the Capability Firewall (20 §4).

    Every field in the documented example is required except
    ``approval_state`` (documented as ``approved|null``).
    """

    actor: ActorKind
    tenant_id: UUID
    permission: PermissionKey
    resource: ResourceRef
    scope: ScopeRef
    entitlement: EntitlementKey
    approval_state: Literal["approved"] | None = None
    risk_level: BoundedStr
