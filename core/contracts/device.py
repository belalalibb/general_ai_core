"""Device identity contracts (FINAL Phase 2 gap-fix: 41 §5 "Device identity").

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/14_SKILLS_AND_TOOLS.md §6
  (client runtime requirements: device pairing / trust state / permission
  grants / revocation / heartbeat / operation audit; device states —
  closed set, verbatim: paired|trusted|revoked|expired|compromised).
- docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
  §5 (FINAL Phase 2 build list: "Device identity") and §17 (Phase 14
  device-trust verbs: pair / trust / revoke / rotate).
- 20 §6 tenant isolation: the device is tenant-scoped (carries tenant_id).

Field derivation note (explicit, no invention hidden): 03_DOMAIN_MODEL has
no Device entity table — fields below are derived 1:1 from the 14 §6
requirement list (pairing → paired_at; trust state → state/trusted_at;
revocation → revoked_at; heartbeat → last_heartbeat_at) plus the standard
tenancy/identity anchors every tenant-scoped entity carries (20 §6).

Scope boundary (recorded, binding): CONTRACT + core trust-state machine
only. Client-runtime transport, permission grants to devices, heartbeat
scheduling, and tool execution on devices are FINAL Phase 14 (Tool
Fabric / Client Runtime) — NOT built here. What Phase 2 needs is the
IDENTITY of a device and its trust lifecycle, so later phases have a
typed anchor instead of ad-hoc dicts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from core.contracts.base import BoundedStr, ContractModel

# --- Closed sets -------------------------------------------------------------------


class DeviceState(StrEnum):
    """Device trust state (14 §6) — closed set, verbatim."""

    PAIRED = "paired"
    TRUSTED = "trusted"
    REVOKED = "revoked"
    EXPIRED = "expired"
    COMPROMISED = "compromised"


#: Deny-by-default usability rule (41 §1 rule 9): the ONLY state in which a
#: device may be used by later phases (client tools, Phase 14) is TRUSTED.
#: paired = identified but not yet trusted; everything else is a refusal.
USABLE_DEVICE_STATES: frozenset[DeviceState] = frozenset({DeviceState.TRUSTED})

#: Terminal states: no transition may ever leave them (a revoked or
#: compromised device must be re-paired as a NEW device identity — the old
#: identity is burned; this is the anti-resurrection property).
TERMINAL_DEVICE_STATES: frozenset[DeviceState] = frozenset(
    {DeviceState.REVOKED, DeviceState.COMPROMISED}
)

#: The trust-state machine (14 §6 states + 41 §17 verbs pair/trust/revoke/
#: rotate), encoded as DATA — allowed (from, to) transitions. Anything not
#: listed is DENIED (deny-by-default). Derivations, explicit:
#: - pair    => creates a device in PAIRED (not a transition row).
#: - trust   => PAIRED -> TRUSTED.
#: - expire  => TRUSTED -> EXPIRED (trust is time-bounded; expiry is an
#:              honest downgrade, not a punishment state).
#: - re-trust=> EXPIRED -> TRUSTED (rotation of trust after expiry — the
#:              41 §17 "rotate" verb; identity is kept, trust is renewed).
#: - revoke  => PAIRED/TRUSTED/EXPIRED -> REVOKED (terminal).
#: - compromise => any non-terminal -> COMPROMISED (terminal; strictly
#:              stronger than revoke — it also marks the device hostile).
ALLOWED_DEVICE_TRANSITIONS: frozenset[tuple[DeviceState, DeviceState]] = frozenset(
    {
        (DeviceState.PAIRED, DeviceState.TRUSTED),
        (DeviceState.TRUSTED, DeviceState.EXPIRED),
        (DeviceState.EXPIRED, DeviceState.TRUSTED),
        (DeviceState.PAIRED, DeviceState.REVOKED),
        (DeviceState.TRUSTED, DeviceState.REVOKED),
        (DeviceState.EXPIRED, DeviceState.REVOKED),
        (DeviceState.PAIRED, DeviceState.COMPROMISED),
        (DeviceState.TRUSTED, DeviceState.COMPROMISED),
        (DeviceState.EXPIRED, DeviceState.COMPROMISED),
    }
)


# --- Entity ------------------------------------------------------------------------


class Device(ContractModel):
    """Device identity entity (fields derived from 14 §6 — see module note).

    No secret material: pairing/attestation secrets belong to the (later)
    client-runtime handshake and the secret store, never to contracts
    (same rule the identity contracts follow, 20 §5).
    """

    id: UUID
    tenant_id: UUID
    user_id: UUID
    name: BoundedStr
    state: DeviceState = DeviceState.PAIRED
    paired_at: datetime
    trusted_at: datetime | None = None
    revoked_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
