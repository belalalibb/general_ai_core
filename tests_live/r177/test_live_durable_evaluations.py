"""R177-FIX-11 — LIVE Postgres round-trip for the durable evaluation store.

Moved here from ``tests/composition/test_durable_evaluations_r177.py`` at B-G:
the hermetic verifier's skip ceiling is 64 (R168 §4 baseline) and an env-gated
test that skips without ``DATABASE_URL`` would have raised it to 65. The R173
precedent (``green_manifest.json`` ``pytest.last_measured.note``: "tests_live/
(env-gated live tests …) intentionally outside the verifier") applies verbatim.

Run (DATABASE_URL exported in-shell, migrations applied)::

    python -m pytest tests_live/r177 -q -p no:cacheprovider -o addopts="" -rs

Hermetic coverage of the same store (fake async repository over the SAME row
encoders) stays in ``tests/composition/test_durable_evaluations_r177.py``.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from core.contracts.evaluation import EvaluationRecord, GraderResult, GraderType, VerificationLevel

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


def _record() -> EvaluationRecord:
    return EvaluationRecord(
        tenant_id=uuid4(),
        execution_id=uuid4(),
        level=VerificationLevel.VALIDATED,
        score=0.8,
        confidence=None,
        evidence_ref="scenario:abc",
        graders=(GraderResult(type=GraderType.DETERMINISTIC, name="output_present", passed=True),),
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
