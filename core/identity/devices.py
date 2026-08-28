"""Device trust registry (FINAL Phase 2 "Device identity", 41 §5).

In-memory skeleton over the :mod:`core.contracts.device` contract — same
posture as the Phase 2 identity service: behavior behind a small typed
surface, persistence/transport/heartbeat-scheduling are later-phase
bindings (Phase 14 client runtime).

Security decisions (explicit, deny-by-default):

- A transition not listed in ``ALLOWED_DEVICE_TRANSITIONS`` raises
  ``DeviceTransitionDenied`` — including EVERY transition out of a terminal
  state (revoked/compromised devices can never come back; re-pairing
  creates a NEW identity).
- ``is_usable`` is True ONLY for ``trusted`` (41 §1 rule 9) — later phases
  gate client-tool dispatch on this single predicate.
- Unknown device ids raise ``DeviceNotFound`` with no existence oracle
  beyond the id itself (same anti-enumeration posture as execution stores).
- Heartbeats are accepted only from usable devices: a revoked/compromised/
  expired/merely-paired device beaconing is NOT a liveness signal — for
  non-usable states the beacon is refused (and is a Phase 14 audit concern).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from core.contracts.base import utc_now
from core.contracts.device import (
    ALLOWED_DEVICE_TRANSITIONS,
    USABLE_DEVICE_STATES,
    Device,
    DeviceState,
)
from core.identity.errors import IdentityError


class DeviceNotFound(IdentityError):
    """Device id unknown (or not visible to the caller) — deny-by-default."""


class DeviceTransitionDenied(IdentityError):
    """Requested trust-state transition is not in the allowed set."""

    def __init__(self, current: DeviceState, requested: DeviceState) -> None:
        super().__init__(f"transition denied: {current.value} -> {requested.value}")
        self.current = current
        self.requested = requested


class DeviceHeartbeatRefused(IdentityError):
    """Heartbeat from a non-usable device is refused (not a liveness signal)."""


class DeviceRegistry:
    """In-memory device trust registry (skeleton; ports/persistence later)."""

    def __init__(self, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._devices: dict[UUID, Device] = {}
        self._clock = clock

    # -- lifecycle verbs (41 §17: pair / trust / revoke / rotate) ------------------

    def pair(self, *, tenant_id: UUID, user_id: UUID, name: str) -> Device:
        """Create a NEW device identity in the ``paired`` state (14 §6)."""
        device = Device(
            id=uuid4(),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            state=DeviceState.PAIRED,
            paired_at=self._clock(),
        )
        self._devices[device.id] = device
        return device

    def trust(self, device_id: UUID) -> Device:
        """paired -> trusted (and expired -> trusted = trust rotation)."""
        return self._transition(device_id, DeviceState.TRUSTED)

    def expire(self, device_id: UUID) -> Device:
        """trusted -> expired (honest downgrade when trust ages out)."""
        return self._transition(device_id, DeviceState.EXPIRED)

    def revoke(self, device_id: UUID) -> Device:
        """any non-terminal -> revoked (terminal)."""
        return self._transition(device_id, DeviceState.REVOKED)

    def mark_compromised(self, device_id: UUID) -> Device:
        """any non-terminal -> compromised (terminal, hostile)."""
        return self._transition(device_id, DeviceState.COMPROMISED)

    # -- queries -------------------------------------------------------------------

    def get(self, device_id: UUID, *, tenant_id: UUID) -> Device:
        """Tenant-scoped read: a foreign-tenant id behaves exactly like an
        absent id (anti-enumeration parity, 20 §6)."""
        device = self._devices.get(device_id)
        if device is None or device.tenant_id != tenant_id:
            raise DeviceNotFound(str(device_id))
        return device

    def is_usable(self, device_id: UUID, *, tenant_id: UUID) -> bool:
        """The single predicate later phases gate on (True only for trusted)."""
        return self.get(device_id, tenant_id=tenant_id).state in USABLE_DEVICE_STATES

    # -- heartbeat (14 §6) -----------------------------------------------------------

    def heartbeat(self, device_id: UUID, *, tenant_id: UUID) -> Device:
        """Record liveness for a USABLE device; refuse everything else."""
        device = self.get(device_id, tenant_id=tenant_id)
        if device.state not in USABLE_DEVICE_STATES:
            raise DeviceHeartbeatRefused(device.state.value)
        updated = device.model_copy(update={"last_heartbeat_at": self._clock()})
        self._devices[device.id] = updated
        return updated

    # -- internals -----------------------------------------------------------------

    def _transition(self, device_id: UUID, requested: DeviceState) -> Device:
        device = self._devices.get(device_id)
        if device is None:
            raise DeviceNotFound(str(device_id))
        if (device.state, requested) not in ALLOWED_DEVICE_TRANSITIONS:
            raise DeviceTransitionDenied(device.state, requested)
        now = self._clock()
        update: dict[str, object] = {"state": requested}
        if requested is DeviceState.TRUSTED:
            update["trusted_at"] = now
        elif requested in (DeviceState.REVOKED, DeviceState.COMPROMISED):
            update["revoked_at"] = now
        updated = device.model_copy(update=update)
        self._devices[device.id] = updated
        return updated
