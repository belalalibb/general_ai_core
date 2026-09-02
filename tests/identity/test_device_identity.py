"""Device identity tests (FINAL Phase 2 gap-fix, T-IMPL-041).

Authority: 14 §6 (states + requirement list), 41 §5 ("Device identity"),
41 §17 (pair/trust/revoke/rotate verbs), 20 §6 (tenant isolation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.device import (
    ALLOWED_DEVICE_TRANSITIONS,
    TERMINAL_DEVICE_STATES,
    USABLE_DEVICE_STATES,
    Device,
    DeviceState,
)
from core.identity.devices import (
    DeviceHeartbeatRefused,
    DeviceNotFound,
    DeviceRegistry,
    DeviceTransitionDenied,
)

# --- Contract: closed sets and structural rules -------------------------------------


def test_device_state_closed_set_verbatim() -> None:
    """14 §6: paired|trusted|revoked|expired|compromised."""
    assert {s.value for s in DeviceState} == {
        "paired",
        "trusted",
        "revoked",
        "expired",
        "compromised",
    }


def test_only_trusted_is_usable() -> None:
    """41 §1 rule 9 (deny-by-default): usable = {trusted} exactly."""
    assert USABLE_DEVICE_STATES == frozenset({DeviceState.TRUSTED})


def test_terminal_states_have_no_outgoing_transitions() -> None:
    """Anti-resurrection: no allowed transition leaves revoked/compromised."""
    assert TERMINAL_DEVICE_STATES == frozenset({DeviceState.REVOKED, DeviceState.COMPROMISED})
    for src, _dst in ALLOWED_DEVICE_TRANSITIONS:
        assert src not in TERMINAL_DEVICE_STATES


def test_transition_table_is_exactly_the_documented_machine() -> None:
    """The state machine, verbatim — a new row cannot ship untested."""
    assert ALLOWED_DEVICE_TRANSITIONS == frozenset(
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


def test_device_contract_defaults_and_posture() -> None:
    device = Device(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        name="laptop",
        paired_at=datetime.now(UTC),
    )
    assert device.state is DeviceState.PAIRED
    assert device.trusted_at is None and device.revoked_at is None
    with pytest.raises(ValidationError):
        device.state = DeviceState.TRUSTED  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Device.model_validate(
            {
                "id": str(uuid4()),
                "tenant_id": str(uuid4()),
                "user_id": str(uuid4()),
                "name": "x",
                "paired_at": datetime.now(UTC).isoformat(),
                "pairing_secret": "s3cret",  # contracts carry no secret material
            }
        )


def test_contract_module_imports_no_implementation() -> None:
    """41 §4 rule: no Contract imports a specific Implementation."""
    import core.contracts.device as device_module

    source = open(device_module.__file__, encoding="utf-8").read()  # noqa: SIM115
    for line in source.splitlines():
        if line.startswith("from core.") and "core.contracts" not in line:
            raise AssertionError(f"non-contract project import: {line}")


# --- Registry behavior ---------------------------------------------------------------


class _Clock:
    """Deterministic advancing clock."""

    def __init__(self) -> None:
        self.now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


def _registry() -> tuple[DeviceRegistry, _Clock]:
    clock = _Clock()
    return DeviceRegistry(clock=clock), clock


def test_pair_creates_paired_not_usable_device() -> None:
    registry, _ = _registry()
    tenant, user = uuid4(), uuid4()
    device = registry.pair(tenant_id=tenant, user_id=user, name="laptop")
    assert device.state is DeviceState.PAIRED
    # paired ≠ usable: pairing identifies, trust authorizes.
    assert registry.is_usable(device.id, tenant_id=tenant) is False


def test_trust_then_usable_with_trusted_at_stamp() -> None:
    registry, _ = _registry()
    tenant = uuid4()
    device = registry.pair(tenant_id=tenant, user_id=uuid4(), name="laptop")
    trusted = registry.trust(device.id)
    assert trusted.state is DeviceState.TRUSTED
    assert trusted.trusted_at is not None
    assert registry.is_usable(device.id, tenant_id=tenant) is True


def test_expire_then_retrust_rotation() -> None:
    """41 §17 'rotate': trusted -> expired -> trusted keeps the identity."""
    registry, _ = _registry()
    tenant = uuid4()
    device = registry.pair(tenant_id=tenant, user_id=uuid4(), name="laptop")
    registry.trust(device.id)
    expired = registry.expire(device.id)
    assert expired.state is DeviceState.EXPIRED
    assert registry.is_usable(device.id, tenant_id=tenant) is False
    rotated = registry.trust(device.id)
    assert rotated.state is DeviceState.TRUSTED
    assert rotated.id == device.id  # same identity, renewed trust


def test_revoked_device_is_terminal_every_exit_denied() -> None:
    registry, _ = _registry()
    tenant = uuid4()
    device = registry.pair(tenant_id=tenant, user_id=uuid4(), name="laptop")
    revoked = registry.revoke(device.id)
    assert revoked.state is DeviceState.REVOKED
    assert revoked.revoked_at is not None
    for attempt in (registry.trust, registry.expire, registry.revoke, registry.mark_compromised):
        with pytest.raises(DeviceTransitionDenied):
            attempt(device.id)
    assert registry.is_usable(device.id, tenant_id=tenant) is False


def test_compromised_device_is_terminal_and_unusable() -> None:
    registry, _ = _registry()
    tenant = uuid4()
    device = registry.pair(tenant_id=tenant, user_id=uuid4(), name="laptop")
    registry.trust(device.id)
    burned = registry.mark_compromised(device.id)
    assert burned.state is DeviceState.COMPROMISED
    with pytest.raises(DeviceTransitionDenied):
        registry.trust(device.id)
    assert registry.is_usable(device.id, tenant_id=tenant) is False


def test_invalid_transitions_denied_with_state_details() -> None:
    registry, _ = _registry()
    device = registry.pair(tenant_id=uuid4(), user_id=uuid4(), name="laptop")
    # paired -> expired is not a legal edge (expiry only ages out TRUST).
    with pytest.raises(DeviceTransitionDenied) as exc:
        registry.expire(device.id)
    assert exc.value.current is DeviceState.PAIRED
    assert exc.value.requested is DeviceState.EXPIRED


def test_heartbeat_accepted_only_from_trusted() -> None:
    registry, clock = _registry()
    tenant = uuid4()
    device = registry.pair(tenant_id=tenant, user_id=uuid4(), name="laptop")
    with pytest.raises(DeviceHeartbeatRefused):
        registry.heartbeat(device.id, tenant_id=tenant)  # paired: refused
    registry.trust(device.id)
    beaten = registry.heartbeat(device.id, tenant_id=tenant)
    assert beaten.last_heartbeat_at == clock.now
    registry.revoke(device.id)
    with pytest.raises(DeviceHeartbeatRefused):
        registry.heartbeat(device.id, tenant_id=tenant)  # revoked: refused


def test_tenant_scoped_reads_foreign_equals_absent() -> None:
    """20 §6 anti-enumeration parity: foreign-tenant probe == absent probe."""
    registry, _ = _registry()
    owner_tenant, foreign_tenant = uuid4(), uuid4()
    device = registry.pair(tenant_id=owner_tenant, user_id=uuid4(), name="laptop")
    with pytest.raises(DeviceNotFound) as foreign_exc:
        registry.get(device.id, tenant_id=foreign_tenant)
    absent_id = uuid4()
    with pytest.raises(DeviceNotFound) as absent_exc:
        registry.get(absent_id, tenant_id=owner_tenant)
    # Same exception type and message SHAPE (id only) — no oracle.
    assert type(foreign_exc.value) is type(absent_exc.value)
    assert str(foreign_exc.value) == str(device.id)
    assert str(absent_exc.value) == str(absent_id)


def test_unknown_device_transitions_raise_not_found() -> None:
    registry, _ = _registry()
    with pytest.raises(DeviceNotFound):
        registry.trust(uuid4())
