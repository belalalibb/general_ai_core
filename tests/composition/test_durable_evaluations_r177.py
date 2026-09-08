"""R177-FIX-11 — durable evaluation store in the durable profile (G-A07-4).

Before: ``EvaluationPolicyService`` / the admin evaluation reads sat over
``InMemoryEvaluationStore`` in BOTH profiles — the artefacts FIX-08 now
relies on for promotion vanished on restart. After: the durable profile binds
``DurableEvaluationStore`` (sync ``EvaluationStorePort`` surface, bridge
inside) over ``PostgresEvaluationRepository`` writing the EXISTING
``evaluations`` table (migration 0010; no new table needed). The in-memory
store stays the hermetic default.

Hermetic tests use a fake async repository holding the SAME encoded row
payloads the Postgres binding writes and reconstructing through the SAME
decoder — the live Postgres round-trip is env-gated (41 §49).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from apps.composition.evaluations import DurableEvaluationStore
from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.evaluation.errors import DuplicateEvaluation, EvaluationNotFound
from core.evaluation.ports import EvaluationStorePort
from infrastructure.db.repositories.evaluations import (
    PostgresEvaluationRepository,
    _record_values,
    _row_to_record,
)

TENANT = uuid4()
EXECUTION = uuid4()


def _record(**overrides: Any) -> EvaluationRecord:
    values: dict[str, Any] = {
        "tenant_id": TENANT,
        "execution_id": EXECUTION,
        "level": VerificationLevel.VALIDATED,
        "score": 0.8,
        "confidence": None,
        "evidence_ref": "scenario:abc",
        "graders": (
            GraderResult(type=GraderType.DETERMINISTIC, name="output_present", passed=True),
            GraderResult(type=GraderType.MODEL_BASED, name="judge", score=0.8, confidence=0.7),
        ),
    }
    values.update(overrides)
    return EvaluationRecord(**values)


@dataclass
class FakeEvaluationRepository:
    """Dict-backed async repo over the SAME row payloads/decoders as Postgres."""

    rows: dict[tuple[UUID, UUID], dict[str, Any]] = field(default_factory=dict)
    order: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def record(self, evaluation: EvaluationRecord) -> None:
        key = (evaluation.tenant_id, evaluation.id)
        if key in self.rows:
            raise DuplicateEvaluation(evaluation.id)
        self.rows[key] = _record_values(evaluation)
        self.order.append(key)

    async def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        row = self.rows.get((tenant_id, evaluation_id))
        if row is None:
            raise EvaluationNotFound(evaluation_id)
        return _row_to_record(SimpleNamespace(**row))

    async def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        return tuple(
            _row_to_record(SimpleNamespace(**self.rows[key]))
            for key in self.order
            if key[0] == tenant_id and self.rows[key]["execution_id"] == execution_id
        )


class ExplodingRepository:
    async def record(self, evaluation: EvaluationRecord) -> None:
        raise ConnectionError("database unreachable")

    async def get(self, tenant_id: UUID, evaluation_id: UUID) -> EvaluationRecord:
        raise ConnectionError("database unreachable")

    async def list_for_execution(
        self, tenant_id: UUID, execution_id: UUID
    ) -> tuple[EvaluationRecord, ...]:
        raise ConnectionError("database unreachable")


@pytest.fixture
def bridge() -> Iterator[AsyncBridge]:
    b = AsyncBridge()
    try:
        yield b
    finally:
        b.close()


@pytest.fixture
def repository() -> FakeEvaluationRepository:
    return FakeEvaluationRepository()


@pytest.fixture
def store(bridge: AsyncBridge, repository: FakeEvaluationRepository) -> EvaluationStorePort:
    return DurableEvaluationStore(repository=repository, bridge=bridge)


class TestDurableEvaluationStore:
    def test_full_fidelity_round_trip_through_rows(self, store: EvaluationStorePort) -> None:
        record = _record()
        assert store.record(record) == record
        assert store.get(TENANT, record.id) == record
        raw = _record(level=VerificationLevel.RAW, score=None, evidence_ref=None, graders=())
        store.record(raw)
        assert store.get(TENANT, raw.id) == raw

    def test_records_are_evidence_and_never_overwritten(self, store: EvaluationStorePort) -> None:
        record = _record()
        store.record(record)
        with pytest.raises(DuplicateEvaluation):
            store.record(record.model_copy(update={"score": 0.1}))
        assert store.get(TENANT, record.id).score == 0.8

    def test_absent_and_foreign_answer_identically(self, store: EvaluationStorePort) -> None:
        record = _record()
        store.record(record)
        with pytest.raises(EvaluationNotFound):
            store.get(TENANT, uuid4())
        with pytest.raises(EvaluationNotFound):
            store.get(uuid4(), record.id)
        assert store.list_for_execution(uuid4(), EXECUTION) == ()
        assert store.list_for_execution(TENANT, uuid4()) == ()

    def test_list_keeps_recording_order(self, store: EvaluationStorePort) -> None:
        first = _record(level=VerificationLevel.EVALUATED)
        second = _record()
        other = _record(execution_id=uuid4())
        for r in (first, second, other):
            store.record(r)
        assert [r.id for r in store.list_for_execution(TENANT, EXECUTION)] == [first.id, second.id]

    def test_durable_failure_propagates_loudly(self, bridge: AsyncBridge) -> None:
        store = DurableEvaluationStore(repository=ExplodingRepository(), bridge=bridge)
        with pytest.raises(ConnectionError):
            store.record(_record())

    def test_new_store_instance_serves_persisted_state(
        self, bridge: AsyncBridge, repository: FakeEvaluationRepository
    ) -> None:
        before = DurableEvaluationStore(repository=repository, bridge=bridge)
        record = _record()
        before.record(record)
        after = DurableEvaluationStore(repository=repository, bridge=bridge)  # "restart"
        assert after.get(TENANT, record.id) == record
        assert [r.id for r in after.list_for_execution(TENANT, EXECUTION)] == [record.id]


class TestRowEncoding:
    def test_values_match_the_evaluations_table_columns(self) -> None:
        from infrastructure.db.tables import evaluations

        values = _record_values(_record())
        assert set(values) == {c.name for c in evaluations.columns}
        assert values["level"] == "VALIDATED"
        assert values["graders"][0] == {
            "type": "deterministic",
            "name": "output_present",
            "passed": True,
        }

    def test_repository_class_exists_over_a_session_factory(self) -> None:
        assert PostgresEvaluationRepository.__init__.__code__.co_varnames[1] == "session_factory"


def test_runtime_durable_profile_binds_the_durable_store() -> None:
    source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "build_durable_evaluation_store(bindings, bridge)" in source
    # hermetic default preserved in the in-memory branch
    assert "InMemoryEvaluationStore()" in source


def test_no_new_migration_needed_the_0010_table_is_reused() -> None:
    versions = sorted(p.name for p in Path("infrastructure/db/migrations/versions").glob("0*.py"))
    assert versions[-1].startswith("0018_"), versions[-1]


# --- live Postgres round-trip (env-gated, 41 §49) ---------------------------------

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


@requires_live_postgres
class TestLiveEvaluationDurability:
    def test_record_survives_a_new_session(self) -> None:
        from apps.composition.database import build_database_bindings, database_settings_from_env
        from apps.composition.evaluations import build_durable_evaluation_store

        settings = database_settings_from_env(os.environ)
        assert settings is not None
        bindings = build_database_bindings(settings)
        bridge = AsyncBridge()
        try:
            store = build_durable_evaluation_store(bindings, bridge)
            record = _record()
            store.record(record)
            again = build_durable_evaluation_store(bindings, bridge)
            assert again.get(record.tenant_id, record.id) == record
        finally:
            bridge.close()
