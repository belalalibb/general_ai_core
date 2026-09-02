"""Audit contract + audit-log port tests (MVP Phase 3, 41 §42; 20 §9; 21 §8).

Any "secret-looking" value here is an obviously-fake placeholder (20 §5).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.audit import AuditLogPort, InMemoryAuditLog, InvalidAuditEvent
from core.contracts import (
    ADMIN_CHANGE_EVENT_TYPES,
    AdminChangeRecord,
    AuditEvent,
    AuditEventType,
)

TENANT_A = uuid4()
TENANT_B = uuid4()
ACTOR = uuid4()


def make_event(
    event_type: AuditEventType = AuditEventType.LOGIN,
    tenant_id=TENANT_A,
    **kwargs,
) -> AuditEvent:
    return AuditEvent(tenant_id=tenant_id, event_type=event_type, **kwargs)


def make_admin_record() -> AdminChangeRecord:
    return AdminChangeRecord(
        what="model_policy",
        previous_version="v41",
        new_version="v42",
        validation_result="passed",
        impact_preview="3 routes re-priced",
        rollback_target="v41",
    )


@pytest.fixture()
def log() -> InMemoryAuditLog:
    return InMemoryAuditLog()


class TestContract:
    def test_event_set_is_closed_and_carries_20s9_verbatim(self) -> None:
        """20 §9 must-audit list — compound lines expanded, nothing else."""
        assert {e.value for e in AuditEventType} == {
            "login",
            "logout",
            "credential_created",
            "credential_revoked",
            "provider_account_used",
            "permission_denied",
            "tool_call",
            "approval_decision",
            "admin_config_published",
            "admin_config_rolled_back",
            "security_policy_changed",
            "training_dataset_promoted",
            "cross_tenant_access_denied",
        }

    def test_admin_change_event_types_subset(self) -> None:
        assert ADMIN_CHANGE_EVENT_TYPES == {
            AuditEventType.ADMIN_CONFIG_PUBLISHED,
            AuditEventType.ADMIN_CONFIG_ROLLED_BACK,
        }

    def test_event_is_immutable(self) -> None:
        event = make_event()
        with pytest.raises(ValidationError):
            event.event_type = AuditEventType.LOGOUT  # type: ignore[misc]

    def test_unknown_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditEvent(
                tenant_id=TENANT_A,
                event_type=AuditEventType.LOGIN,
                surprise="nope",  # type: ignore[call-arg]
            )

    def test_defaults(self) -> None:
        event = make_event()
        assert event.actor_id is None  # system-initiated by default
        assert event.details == {}
        assert event.admin_change is None
        assert event.occurred_at.tzinfo is not None

    def test_admin_change_record_carries_21s8_fields(self) -> None:
        record = make_admin_record()
        assert record.what == "model_policy"
        assert record.previous_version == "v41"
        assert record.new_version == "v42"
        assert record.validation_result == "passed"
        assert record.impact_preview == "3 routes re-priced"
        assert record.rollback_target == "v41"

    def test_details_carry_credential_ref_not_value(self) -> None:
        """20 §5 discipline: details reference secrets by ref only."""
        event = make_event(
            AuditEventType.CREDENTIAL_CREATED,
            details={"credential_ref": "credref_fake-placeholder"},
        )
        assert event.details["credential_ref"].startswith("credref_")


class TestAppendOnly:
    def test_satisfies_port_protocol(self, log: InMemoryAuditLog) -> None:
        port: AuditLogPort = log
        assert isinstance(port, InMemoryAuditLog)

    def test_append_and_read_round_trip(self, log: InMemoryAuditLog) -> None:
        event = make_event()
        stored = log.append(event)
        assert stored == event
        assert log.read(TENANT_A) == (event,)

    def test_port_has_no_mutation_surface(self, log: InMemoryAuditLog) -> None:
        """Append-only by design: no update/delete/clear methods exist."""
        for forbidden in ("update", "delete", "remove", "clear", "truncate"):
            assert not hasattr(log, forbidden)

    def test_admin_event_requires_admin_record(self, log: InMemoryAuditLog) -> None:
        for event_type in ADMIN_CHANGE_EVENT_TYPES:
            with pytest.raises(InvalidAuditEvent):
                log.append(make_event(event_type))

    def test_admin_event_with_record_accepted(self, log: InMemoryAuditLog) -> None:
        event = make_event(
            AuditEventType.ADMIN_CONFIG_PUBLISHED,
            actor_id=ACTOR,
            admin_change=make_admin_record(),
        )
        assert log.append(event) == event

    def test_non_admin_event_rejects_admin_record(self, log: InMemoryAuditLog) -> None:
        with pytest.raises(InvalidAuditEvent):
            log.append(make_event(AuditEventType.LOGIN, admin_change=make_admin_record()))


class TestReads:
    def test_chronological_order(self, log: InMemoryAuditLog) -> None:
        t1 = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
        t2 = datetime(2026, 8, 25, 11, 0, tzinfo=UTC)
        late = make_event(AuditEventType.LOGOUT, occurred_at=t2)
        early = make_event(AuditEventType.LOGIN, occurred_at=t1)
        log.append(late)  # appended out of order on purpose
        log.append(early)
        assert log.read(TENANT_A) == (early, late)

    def test_filter_by_event_type(self, log: InMemoryAuditLog) -> None:
        login = make_event(AuditEventType.LOGIN)
        denied = make_event(AuditEventType.PERMISSION_DENIED)
        log.append(login)
        log.append(denied)
        assert log.read(TENANT_A, event_type=AuditEventType.PERMISSION_DENIED) == (denied,)

    def test_limit_keeps_newest(self, log: InMemoryAuditLog) -> None:
        t = lambda h: datetime(2026, 8, 25, h, 0, tzinfo=UTC)  # noqa: E731
        events = [make_event(occurred_at=t(h)) for h in (9, 10, 11)]
        for event in events:
            log.append(event)
        assert log.read(TENANT_A, limit=2) == (events[1], events[2])

    def test_count(self, log: InMemoryAuditLog) -> None:
        assert log.count(TENANT_A) == 0
        log.append(make_event())
        log.append(make_event(AuditEventType.LOGOUT))
        assert log.count(TENANT_A) == 2


class TestTenantIsolation:
    """20 §6: reads never cross tenants."""

    def test_reads_are_tenant_scoped(self, log: InMemoryAuditLog) -> None:
        event_a = make_event(tenant_id=TENANT_A)
        event_b = make_event(tenant_id=TENANT_B)
        log.append(event_a)
        log.append(event_b)
        assert log.read(TENANT_A) == (event_a,)
        assert log.read(TENANT_B) == (event_b,)

    def test_count_is_tenant_scoped(self, log: InMemoryAuditLog) -> None:
        log.append(make_event(tenant_id=TENANT_A))
        assert log.count(TENANT_B) == 0

    def test_cross_tenant_denial_recorded_in_probed_tenant(self, log: InMemoryAuditLog) -> None:
        denial = make_event(
            AuditEventType.CROSS_TENANT_ACCESS_DENIED,
            tenant_id=TENANT_A,
            details={"probing_actor": str(ACTOR)},
        )
        log.append(denial)
        assert log.read(TENANT_A) == (denial,)
        assert log.read(TENANT_B) == ()
