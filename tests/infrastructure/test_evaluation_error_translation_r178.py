"""Exercise the real repository with injected SQLAlchemy errors; no live DB claim."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from core.contracts.evaluation import EvaluationRecord, VerificationLevel
from core.evaluation.errors import DuplicateEvaluation
from infrastructure.db.repositories.evaluations import PostgresEvaluationRepository
from infrastructure.db.tables import evaluations


def _attempt(error: IntegrityError) -> None:
    session = MagicMock()
    session.execute = AsyncMock(side_effect=error)
    factory = MagicMock()
    factory.return_value.__aenter__.return_value = session
    repository = PostgresEvaluationRepository(factory)
    record = EvaluationRecord(
        tenant_id=uuid4(), execution_id=uuid4(), level=VerificationLevel.RAW
    )
    asyncio.run(repository.record(record))


def test_migrated_primary_key_collision_has_domain_error() -> None:
    # Matches migration 0010 and the shared SQLAlchemy metadata, not a guessed name.
    assert evaluations.primary_key.name == "pk_evaluations"
    error = IntegrityError(
        "INSERT", {}, Exception('duplicate key violates unique constraint "pk_evaluations"')
    )
    with pytest.raises(DuplicateEvaluation) as caught:
        _attempt(error)
    assert caught.value.__cause__ is error


@pytest.mark.parametrize(
    "constraint",
    ["fk_evaluations_execution_id_executions", "ck_evaluations_level_closed_set"],
)
def test_unrelated_integrity_errors_are_not_duplicates(constraint: str) -> None:
    error = IntegrityError("INSERT", {}, Exception(f'violates constraint "{constraint}"'))
    with pytest.raises(IntegrityError) as caught:
        _attempt(error)
    assert caught.value is error
