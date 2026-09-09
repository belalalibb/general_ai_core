"""R177-FIX-10 — structured knowledge intake adapter (G-A07-3).

Before: knowledge entered the learning lifecycle one item per admin call
(``POST /v1/admin/learning/samples``); no CSV/JSON batch path existed. After:
``apps/api/intake.py`` parses CSV or JSON rows, validates the batch against
DECLARED expectations (required columns, key column, max rows), and feeds
each admitted row to the EXISTING ``capture_external`` — every item lands RAW
and immediately gets the deterministic 22 §12 secret scan recorded on it, so
a secret-shaped cell is flagged at intake and can never be marked sanitized
(the existing gate refuses ``passed=True`` with findings). Refused rows and
the validation report come back as one intake report; an over-limit or
malformed batch is QUARANTINED — nothing is captured.

Enforcement points are unchanged: sanitizer + TrainingEligibilityGate.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.intake import (
    INTAKE_FORMATS,
    IntakeAdapter,
    IntakeExpectations,
    parse_intake_rows,
)
from core.contracts.learning import SanitizationState
from core.evaluation.memory import InMemoryEvaluationStore
from core.evaluation.policy import EvaluationPolicyService
from core.execution.service import ExecutionService
from core.learning.gates import TrainingEligibilityGate
from core.learning.lifecycle import LearningLifecycleService, SanitizationRefused
from core.memory.memory import InMemoryMemoryStore
from tests.api.test_admin_api import World, _no_sleep

TENANT = uuid4()
# Secret-SHAPED, never a real credential: 36 base62 chars after the prefix.
FAKE_PAT = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _lifecycle() -> LearningLifecycleService:
    return LearningLifecycleService(
        evaluation=EvaluationPolicyService(store=InMemoryEvaluationStore()),
        knowledge=InMemoryMemoryStore(),
        audit=None,
        eligibility_gate=TrainingEligibilityGate(),
    )


def _expectations(**overrides: Any) -> IntakeExpectations:
    values: dict[str, Any] = {
        "required_columns": ("topic", "answer"),
        "key_column": "topic",
        "max_rows": 5,
    }
    values.update(overrides)
    return IntakeExpectations(**values)


CSV = "topic,answer\nfaq.hours,Open 9-5\nfaq.refunds,30 days\n"
JSON_ROWS = (
    '[{"topic": "faq.hours", "answer": "Open 9-5"}, {"topic": "faq.refunds", "answer": "30 days"}]'
)


# --- parsing -------------------------------------------------------------------------------


class TestParsing:
    def test_formats_are_a_closed_set(self) -> None:
        assert INTAKE_FORMATS == frozenset({"csv", "json"})

    def test_csv_and_json_parse_to_identical_rows(self) -> None:
        assert parse_intake_rows("csv", CSV) == parse_intake_rows("json", JSON_ROWS)
        assert parse_intake_rows("csv", CSV)[0] == {"topic": "faq.hours", "answer": "Open 9-5"}

    @pytest.mark.parametrize(
        "bad", ['{"topic": "x"}', "[1, 2]", '[{"topic": {"nested": 1}}]', "not json"]
    )
    def test_json_must_be_an_array_of_flat_objects(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_intake_rows("json", bad)

    def test_unknown_format_refused(self) -> None:
        with pytest.raises(ValueError, match="xlsx"):
            parse_intake_rows("xlsx", "")


# --- adapter -------------------------------------------------------------------------------


class TestAdapter:
    def test_admitted_rows_land_raw_with_a_recorded_scan(self) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        report = adapter.ingest(TENANT, expectations=_expectations(), format="csv", content=CSV)
        assert report.quarantined is False
        assert [a.knowledge_key for a in report.admitted] == ["faq.hours", "faq.refunds"]
        assert report.refused == ()
        assert all(a.scan_clean for a in report.admitted)
        samples = lifecycle.list_samples(TENANT)
        assert len(samples) == 2
        for sample in samples:
            assert sample.verification_level.value == "RAW"
            assert sample.sanitization_state is SanitizationState.PENDING
            view = lifecycle.sample_report(TENANT, sample.id)
            assert view["source_kind"] == "external"
            assert view["sanitization_report"] is not None
            assert view["sanitization_report"]["clean"] is True

    def test_secret_shaped_cell_is_flagged_at_intake_and_never_passes_sanitization(
        self,
    ) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        content = f"topic,answer\nfaq.token,{FAKE_PAT}\nfaq.hours,Open 9-5\n"
        report = adapter.ingest(TENANT, expectations=_expectations(), format="csv", content=content)
        flagged = [a for a in report.admitted if not a.scan_clean]
        assert [a.knowledge_key for a in flagged] == ["faq.token"]
        assert report.flagged == 1
        # Findings name path + label only — never the cell content.
        assert FAKE_PAT not in str(flagged[0].findings)
        assert "github_pat" in str(flagged[0].findings)
        assert FAKE_PAT not in str(report.as_json())
        # The EXISTING gate refuses the reviewed pass while findings exist ⇒
        # the sample can never become eligible for promotion.
        sample_id = UUID(flagged[0].sample_id)
        with pytest.raises(SanitizationRefused):
            lifecycle.mark_sanitized(TENANT, sample_id, passed=True)
        state = lifecycle.sample_report(TENANT, sample_id)["sample"]["sanitization_state"]
        assert state == "failed"

    def test_rows_missing_required_columns_are_refused_not_captured(self) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        content = "topic,answer\nfaq.hours,Open 9-5\n,no key\nfaq.blank,\n"
        report = adapter.ingest(TENANT, expectations=_expectations(), format="csv", content=content)
        assert [a.knowledge_key for a in report.admitted] == ["faq.hours"]
        assert [(r.row, r.reason) for r in report.refused] == [
            (2, "missing required column(s): topic"),
            (3, "missing required column(s): answer"),
        ]
        assert len(lifecycle.list_samples(TENANT)) == 1

    def test_over_limit_batch_is_quarantined_nothing_captured(self) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        rows = "\n".join(f"k{i},v{i}" for i in range(6))
        report = adapter.ingest(
            TENANT,
            expectations=_expectations(max_rows=5),
            format="csv",
            content=f"topic,answer\n{rows}\n",
        )
        assert report.quarantined is True
        assert report.quarantine_reason == "batch has 6 rows; max_rows is 5"
        assert report.admitted == () and report.refused == ()
        assert lifecycle.list_samples(TENANT) == ()

    def test_malformed_content_is_quarantined(self) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        report = adapter.ingest(TENANT, expectations=_expectations(), format="json", content="[1]")
        assert report.quarantined is True
        assert report.quarantine_reason is not None
        assert lifecycle.list_samples(TENANT) == ()

    def test_key_column_must_be_required(self) -> None:
        with pytest.raises(ValueError, match="key_column"):
            _expectations(key_column="id")

    def test_report_is_json_and_counts_add_up(self) -> None:
        lifecycle = _lifecycle()
        adapter = IntakeAdapter(lifecycle=lifecycle)
        content = f"topic,answer\nfaq.hours,Open 9-5\n,x\nfaq.token,{FAKE_PAT}\n"
        report = adapter.ingest(TENANT, expectations=_expectations(), format="csv", content=content)
        body = report.as_json()
        assert body["rows"] == 3
        assert len(body["admitted"]) == 2 and len(body["refused"]) == 1
        assert body["flagged"] == 1
        assert body["quarantined"] is False
        assert body["quarantine_reason"] is None


# --- route ---------------------------------------------------------------------------------


def _app(world: World) -> FastAPI:
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=world.router,
        execution_service=service,
        principal=world.principal,
        admin=dataclasses.replace(world.surface(), audit=world.audit),
        memory=InMemoryMemoryStore(),
    )


async def _post(app: FastAPI, path: str, body: dict[str, object]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post(path, json=body)


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.get(path)


INTAKE = "/v1/admin/learning/intake"
EXPECTATIONS = {"required_columns": ["topic", "answer"], "key_column": "topic", "max_rows": 10}


class TestRoute:
    def test_batch_intake_then_samples_visible_through_existing_reads(self) -> None:
        world = World()
        app = _app(world)
        response = run(
            _post(
                app, INTAKE, {"format": "json", "content": JSON_ROWS, "expectations": EXPECTATIONS}
            )
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["quarantined"] is False
        assert len(body["admitted"]) == 2
        listed = run(_get(app, "/v1/admin/learning/samples"))
        assert len(listed.json()["samples"]) == 2
        detail = run(_get(app, f"/v1/admin/learning/samples/{body['admitted'][0]['sample_id']}"))
        assert detail.status_code == 200
        assert detail.json()["source_kind"] == "external"
        assert detail.json()["sanitization_report"]["clean"] is True

    def test_quarantined_batch_is_422_and_captures_nothing(self) -> None:
        world = World()
        app = _app(world)
        response = run(
            _post(
                app,
                INTAKE,
                {"format": "csv", "content": CSV, "expectations": {**EXPECTATIONS, "max_rows": 1}},
            )
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
        assert "max_rows" in response.json()["error"]["message"]
        assert run(_get(app, "/v1/admin/learning/samples")).json()["samples"] == []

    def test_unknown_format_and_oversized_content_are_422(self) -> None:
        app = _app(World())
        bad_format = run(
            _post(app, INTAKE, {"format": "xlsx", "content": "", "expectations": EXPECTATIONS})
        )
        assert bad_format.status_code == 422
        oversized = run(
            _post(
                app,
                INTAKE,
                {
                    "format": "csv",
                    "content": "topic,answer\n" + "x" * 300_000,
                    "expectations": EXPECTATIONS,
                },
            )
        )
        assert oversized.status_code == 422

    def test_non_admin_denied(self) -> None:
        app = _app(World(is_admin=False))
        response = run(
            _post(app, INTAKE, {"format": "csv", "content": CSV, "expectations": EXPECTATIONS})
        )
        assert response.status_code in (401, 403)
