"""R184 / Q7 option (a) — ``evaluation_status`` served on the execution admin read.

The execution admin read in this repository is the per-execution row set of
``GET /v1/admin/usage`` (R182_READINESS §4 row 18; there is no
``/v1/admin/executions/{id}`` route). Each row gains an ADDITIVE
``evaluation_status`` ∈ {NEVER_EVALUATED, EVALUATED} derived from the
tenant-scoped evaluation store. Preserved, byte-for-byte:

- ``GET /v1/admin/executions/{id}/evaluations`` still answers ``[]`` for
  "no evaluations" AND for unknown/foreign executions (anti-enumeration,
  20 §6 — core/evaluation/ports.py);
- ``GET /v1/executions/{id}`` (user read, 22 §7 "user sees final result
  only") carries no evaluation field;
- the admin usage row is computed only over rows the tenant-scoped
  ``store.list`` already returns (no foreign row, no new lookup surface).

Written RED before the production edit.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from core.contracts.evaluation import (
    EvaluationRecord,
    GraderResult,
    GraderType,
    VerificationLevel,
)
from core.contracts.execute import ExecutionStatus
from tests.api.test_aa1_api_seams import (
    ADMIN_EMAIL,
    USER_EMAIL,
    InMemoryExecutionStore,
    _client,
    _login,
    _seed_execution,
    bearer,
    make_session_app,
    run,
)


def _graded(tenant_id: UUID, execution_id: UUID) -> EvaluationRecord:
    return EvaluationRecord(
        tenant_id=tenant_id,
        execution_id=execution_id,
        level=VerificationLevel.EVALUATED,
        graders=(GraderResult(type=GraderType.DETERMINISTIC, name="schema_check", passed=True),),
    )


def _raw(tenant_id: UUID, execution_id: UUID) -> EvaluationRecord:
    return EvaluationRecord(
        tenant_id=tenant_id, execution_id=execution_id, level=VerificationLevel.RAW
    )


class TestAdminUsageEvaluationStatus:
    def test_rows_carry_the_closed_status_never_evaluated_by_default(self) -> None:
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            _seed_execution(store, tenant_id=session.tenant_id)
            async with _client(app) as c:
                response = await c.get("/v1/admin/usage", headers=bearer(token))
                assert response.status_code == 200
                rows = response.json()["usage"]
                assert len(rows) == 1
                assert rows[0]["evaluation_status"] == "NEVER_EVALUATED"
                # additive: the recorded USG-2 keys are all still there
                assert {"execution_id", "status", "created_at", "ledger"} <= set(rows[0])

        run(scenario())

    def test_raw_record_does_not_count_as_evaluated_but_graded_record_does(self) -> None:
        store = InMemoryExecutionStore()
        app, identity, world = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            tenant = session.tenant_id
            only_raw = _seed_execution(store, tenant_id=tenant)
            graded = _seed_execution(store, tenant_id=tenant)
            world.evaluations.record(_raw(tenant, only_raw))
            world.evaluations.record(_raw(tenant, graded))
            world.evaluations.record(_graded(tenant, graded))
            async with _client(app) as c:
                response = await c.get("/v1/admin/usage", headers=bearer(token))
                rows = response.json()["usage"]
                by_id = {r["execution_id"]: r["evaluation_status"] for r in rows}
                assert by_id == {str(only_raw): "NEVER_EVALUATED", str(graded): "EVALUATED"}

        run(scenario())

    def test_status_is_derived_only_from_the_callers_tenant(self) -> None:
        """A foreign tenant's graded record must not leak into a same-id lookup."""
        store = InMemoryExecutionStore()
        app, identity, world = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            own = _seed_execution(store, tenant_id=session.tenant_id)
            foreign_tenant = uuid4()
            _seed_execution(store, tenant_id=foreign_tenant)
            # a graded record under a FOREIGN tenant that reuses the caller's execution id
            world.evaluations.record(_graded(foreign_tenant, own))
            async with _client(app) as c:
                response = await c.get("/v1/admin/usage", headers=bearer(token))
                rows = response.json()["usage"]
                assert [r["execution_id"] for r in rows] == [str(own)]
                assert rows[0]["evaluation_status"] == "NEVER_EVALUATED"

        run(scenario())

    def test_evaluation_list_route_and_user_read_are_unchanged(self) -> None:
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            admin_token = await _login(app, ADMIN_EMAIL)
            user_token = await _login(app, USER_EMAIL)
            session = identity.resolve_session(admin_token)
            own = _seed_execution(store, tenant_id=session.tenant_id)
            unknown = uuid4()
            async with _client(app) as c:
                # anti-enumeration preserved: own-without-evaluations == unknown == []
                own_list = await c.get(
                    f"/v1/admin/executions/{own}/evaluations", headers=bearer(admin_token)
                )
                unknown_list = await c.get(
                    f"/v1/admin/executions/{unknown}/evaluations", headers=bearer(admin_token)
                )
                assert own_list.status_code == unknown_list.status_code == 200
                assert own_list.json() == unknown_list.json() == {"evaluations": []}
                assert "evaluation_status" not in own_list.text
                # user read (22 §7): no evaluation field of any kind
                user_session = identity.resolve_session(user_token)
                # RUNNING: the by-id read renders status/progress only (a seeded
                # SUCCEEDED row has no nodes, so final_output cannot be derived).
                user_exec = _seed_execution(
                    store, tenant_id=user_session.tenant_id, status=ExecutionStatus.RUNNING
                )
                status = await c.get(f"/v1/executions/{user_exec}", headers=bearer(user_token))
                assert status.status_code == 200
                assert "evaluation_status" not in status.json()

        run(scenario())
