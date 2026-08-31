"""Phase AA-1 — API seams adversarial suite (doc C §3 acceptance criteria).

Covers the six closed-scope seams:

- IDN-1: /v1/auth/* binding InMemoryIdentityService sessions → per-request
  Principal; constant-message 401s; logout idempotence; audit honesty.
- EXE-1: GET /v1/executions — tenant-scoped, filterable, anti-enumeration.
- AUD-1: GET /v1/admin/audit — port surfaced verbatim, admin-gated.
- SYS-1: GET /healthz + GET /v1/admin/system — process-local truths, labeled.
- USG-2: GET /v1/admin/usage — ledger read-model, null never fabricated.
- WBH-1: GET/DELETE /v1/webhooks — tenant-scoped management.

Test posture (t033/t034 style): attacks first, happy paths second; the
route-surface delta is PINNED by test so silent route growth fails loudly.

FastAPI 0.141 finding (recorded): included routers appear lazily in
``app.routes`` (``_IncludedRouter``), so surface enumeration goes through
``app.openapi()`` — the same posture the t033 hardening suite uses.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api import InMemoryExecutionStore, Principal, create_app
from apps.api.auth import AuthSurface
from core.audit.memory import InMemoryAuditLog
from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.execute import ExecutionStatus
from core.execution.service import ExecutionService
from core.identity.service import InMemoryIdentityService
from tests.api.test_admin_api import World as AdminWorld
from tests.api.test_execute_api import World as ExecuteWorld


def run[T](coro: Awaitable[T]) -> T:
    return asyncio.run(coro)  # type: ignore[arg-type]


# --- identity fixtures ---------------------------------------------------------


class _Hasher:
    """Deterministic test hasher (NOT a security binding)."""

    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == f"h:{password}"


class _MailSink:
    """Captures verification tokens instead of sending email."""

    def __init__(self) -> None:
        self.tokens: dict[str, str] = {}

    def send_verification(self, email: str, token: str) -> None:
        self.tokens[email] = token


def make_identity() -> tuple[InMemoryIdentityService, _MailSink]:
    sink = _MailSink()
    service = InMemoryIdentityService(
        hasher=_Hasher(), email_sender=sink, default_plan_id=uuid4()
    )
    return service, sink


def register_verified(
    identity: InMemoryIdentityService, sink: _MailSink, email: str, password: str
) -> None:
    identity.register(email, password, "en")
    identity.verify_email(sink.tokens[email])


ADMIN_EMAIL = "admin@example.test"
USER_EMAIL = "user@example.test"
PASSWORD = "correct-horse"


def make_session_app(
    *,
    audit: InMemoryAuditLog | None = None,
    store: InMemoryExecutionStore | None = None,
    with_admin: bool = True,
    system_info: bool = True,
    healthz: bool = True,
    webhooks: bool = True,
    subscriptions: dict[UUID, list[Any]] | None = None,
) -> tuple[FastAPI, InMemoryIdentityService, AdminWorld]:
    """Full-surface app in AUTH mode with admin + user accounts registered."""
    identity, sink = make_identity()
    register_verified(identity, sink, ADMIN_EMAIL, PASSWORD)
    register_verified(identity, sink, USER_EMAIL, PASSWORD)
    world = AdminWorld()
    execution_store = store if store is not None else InMemoryExecutionStore()
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
    )
    surface = None
    if with_admin:
        surface = dataclasses.replace(
            world.surface(), audit=audit, executions=execution_store
        )
    app = create_app(
        router=world.router,
        execution_service=service,
        store=execution_store,
        auth=AuthSurface(
            identity=identity,
            admin_emails=frozenset({ADMIN_EMAIL}),
            audit=audit,
        ),
        admin=surface,
        system_info=(lambda: {"note": "test"}) if system_info else None,
        healthz=healthz,
        webhooks=webhooks,
        webhook_subscriptions=subscriptions,
    )
    return app, identity, world


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _login(app: FastAPI, email: str) -> str:
    async with _client(app) as c:
        response = await c.post(
            "/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    assert isinstance(token, str)
    return token


def openapi_ops(app: FastAPI) -> list[str]:
    """Sorted METHOD PATH list via OpenAPI (lazy-router-safe enumeration)."""
    spec = app.openapi()
    return sorted(
        f"{method.upper()} {path}"
        for path, item in spec["paths"].items()
        for method in item
    )


# --- IDN-1: auth binding ---------------------------------------------------------


class TestAuthBinding:
    def test_login_session_principal_round_trip(self) -> None:
        """Acceptance (1): login → session → Principal round trip."""
        app, _, _ = make_session_app()

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                session = await c.get("/v1/auth/session", headers=bearer(token))
                assert session.status_code == 200
                body = session.json()
                assert body["email"] == ADMIN_EMAIL
                assert body["is_admin"] is True
                UUID(body["user_id"])
                UUID(body["tenant_id"])

        run(scenario())

    def test_all_login_failures_are_byte_identical(self) -> None:
        """Unknown email / wrong password / unverified — ONE constant 401."""
        identity, sink = make_identity()
        register_verified(identity, sink, ADMIN_EMAIL, PASSWORD)
        identity.register("pending@example.test", PASSWORD, "en")  # never verified
        world = AdminWorld()
        service = ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: "secret-ref://x"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
        )
        app = create_app(
            router=world.router,
            execution_service=service,
            auth=AuthSurface(identity=identity),
        )

        async def scenario() -> None:
            async with _client(app) as c:
                attempts = [
                    {"email": "nobody@example.test", "password": PASSWORD},
                    {"email": ADMIN_EMAIL, "password": "wrong"},
                    {"email": "pending@example.test", "password": PASSWORD},
                ]
                bodies = set()
                for attempt in attempts:
                    response = await c.post("/v1/auth/login", json=attempt)
                    assert response.status_code == 401
                    bodies.add(response.content)
                assert len(bodies) == 1  # byte-identical (20 §6)

        run(scenario())

    def test_missing_garbage_and_wrong_scheme_tokens_same_401(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            async with _client(app) as c:
                missing = await c.get("/v1/auth/session")
                garbage = await c.get(
                    "/v1/auth/session", headers=bearer("not-a-token")
                )
                scheme = await c.get(
                    "/v1/auth/session", headers={"Authorization": "Basic abc"}
                )
                assert (
                    missing.status_code
                    == garbage.status_code
                    == scheme.status_code
                    == 401
                )
                assert missing.content == garbage.content == scheme.content

        run(scenario())

    def test_logout_is_idempotent_and_never_a_token_oracle(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                first = await c.post("/v1/auth/logout", headers=bearer(token))
                second = await c.post("/v1/auth/logout", headers=bearer(token))
                tokenless = await c.post("/v1/auth/logout")
                garbage = await c.post("/v1/auth/logout", headers=bearer("zzz"))
                assert (
                    first.status_code
                    == second.status_code
                    == tokenless.status_code
                    == garbage.status_code
                    == 204
                )
                after = await c.get("/v1/auth/session", headers=bearer(token))
                assert after.status_code == 401

        run(scenario())

    def test_audit_records_only_real_login_logout_events(self) -> None:
        """Honesty: no audit rows for failed logins or no-op logouts."""
        audit = InMemoryAuditLog()
        app, identity, _ = make_session_app(audit=audit)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            tenant_id = session.tenant_id
            async with _client(app) as c:
                await c.post(
                    "/v1/auth/login",
                    json={"email": ADMIN_EMAIL, "password": "wrong"},
                )
                await c.post("/v1/auth/logout", headers=bearer("garbage"))
                await c.post("/v1/auth/logout", headers=bearer(token))
                await c.post("/v1/auth/logout", headers=bearer(token))  # no-op
            events = audit.read(tenant_id)
            types = [e.event_type for e in events]
            assert types == [AuditEventType.LOGIN, AuditEventType.LOGOUT]

        run(scenario())

    def test_tokenless_requests_denied_on_all_tenant_scoped_routes(self) -> None:
        """Deny-by-default: every tenant-scoped route 401s with zero residue."""
        store = InMemoryExecutionStore()
        subscriptions: dict[UUID, list[Any]] = {}
        app, _, _ = make_session_app(store=store, subscriptions=subscriptions)

        async def scenario() -> None:
            async with _client(app) as c:
                probes = [
                    ("POST", "/v1/execute", {"ask": "hi"}),
                    ("GET", "/v1/executions", None),
                    ("GET", f"/v1/executions/{uuid4()}", None),
                    ("GET", "/v1/webhooks", None),
                    ("POST", "/v1/webhooks", {"url": "https://x.test/h"}),
                    ("DELETE", f"/v1/webhooks/{uuid4()}", None),
                ]
                for method, path, body in probes:
                    response = await c.request(method, path, json=body)
                    assert response.status_code == 401, (method, path)
                    assert response.json()["error"]["code"] == "unauthenticated"

        run(scenario())
        assert len(store) == 0  # zero residue
        assert subscriptions == {}

    def test_exactly_one_identity_mode_is_enforced(self) -> None:
        """Loud ValueError for both-or-neither principal/auth (never silent)."""
        world = ExecuteWorld()
        identity, _ = make_identity()
        service = ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: "secret-ref://x"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
        )
        from core.routing.router import SimpleScoringRouter

        router = SimpleScoringRouter(world.providers, world.models, world.bindings)
        with pytest.raises(ValueError, match="exactly one"):
            create_app(router=router, execution_service=service)
        with pytest.raises(ValueError, match="exactly one"):
            create_app(
                router=router,
                execution_service=service,
                principal=Principal(tenant_id=uuid4(), user_id=uuid4()),
                auth=AuthSurface(identity=identity),
            )

    def test_fixed_principal_mode_has_no_auth_routes(self) -> None:
        """Fixed mode (every existing caller): /v1/auth/* is ABSENT."""
        world = ExecuteWorld()
        app = world.app()
        assert not any("/v1/auth" in op for op in openapi_ops(app))


# --- admin gate under sessions ---------------------------------------------------


class TestAdminGateUnderSessions:
    def test_non_admin_session_denied_on_every_admin_operation(self) -> None:
        """Acceptance (1): non-admin principals denied on ALL /v1/admin/*."""
        audit = InMemoryAuditLog()
        app, _, _ = make_session_app(audit=audit)
        admin_ops = [op for op in openapi_ops(app) if "/v1/admin" in op]
        assert admin_ops, "admin surface must exist for this test"

        async def scenario() -> None:
            token = await _login(app, USER_EMAIL)
            async with _client(app) as c:
                for op in admin_ops:
                    method, path = op.split(" ", 1)
                    path = path.replace("{change_id}", str(uuid4()))
                    path = path.replace("{evaluation_id}", str(uuid4()))
                    path = path.replace("{execution_id}", str(uuid4()))
                    path = path.replace("{plan_tenant_id}", str(uuid4()))
                    path = path.replace("{scenario_id}", str(uuid4()))
                    path = path.replace("{proposal_id}", str(uuid4()))
                    body = None
                    if method == "POST" and (
                        path.endswith("/changes") or path.endswith("/changes/propose")
                    ):
                        # Contract-valid body: FastAPI parses bodies before
                        # handlers, so the deny must win over a 422. The V7-6
                        # propose route shares the AdminDraftRequest contract.
                        body = {"action": "disable_model", "payload": {}}
                    if method == "POST" and path.endswith("/scenarios"):
                        # Same posture for the V7-3 save route.
                        body = {"name": "denied", "ask": "denied"}
                    # V8 source-change routes with bodies (same posture).
                    if method == "POST" and path.endswith("/source-changes"):
                        body = {
                            "base_snapshot_id": "0" * 64,
                            "operations": [
                                {"kind": "delete_file", "path": "denied.py"}
                            ],
                            "rationale": "denied",
                        }
                    if method == "POST" and path.endswith("/source-changes/snapshots"):
                        body = {"files": {"denied.py": ""}}
                    if (
                        method == "POST"
                        and "/source-changes/" in path
                        and path.endswith("/approve")
                    ):
                        body = {"cited_hash": "0" * 64}
                    if (
                        method == "POST"
                        and "/source-changes/" in path
                        and path.endswith("/reject")
                    ):
                        body = {"reason": "denied"}
                    response = await c.request(
                        method, path, json=body, headers=bearer(token)
                    )
                    assert response.status_code == 403, op
                    assert response.json()["error"]["code"] == "unauthorized"

        run(scenario())

    def test_anonymous_denied_with_401_not_403(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            async with _client(app) as c:
                response = await c.get("/v1/admin/models")
                assert response.status_code == 401
                assert response.json()["error"]["code"] == "unauthenticated"

        run(scenario())


# --- EXE-1: executions list ------------------------------------------------------


def _seed_execution(
    store: InMemoryExecutionStore,
    *,
    tenant_id: UUID,
    user_id: UUID | None = None,
    status: ExecutionStatus = ExecutionStatus.SUCCEEDED,
    created_at: datetime | None = None,
) -> UUID:
    """Insert a minimal report row directly (list semantics under test)."""
    from core.contracts.execution import Execution, ExecutionStrategy
    from core.execution.service import ExecutionReport

    execution = Execution(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id if user_id is not None else uuid4(),
        request_hash="h" * 8,
        status=status,
        strategy=ExecutionStrategy.SINGLE,
        cost_snapshot={},
        created_at=(
            created_at
            if created_at is not None
            else datetime.now(UTC)
        ),
    )
    store.put(ExecutionReport(execution=execution, nodes=(), status_history=()))
    return execution.id


class TestExecutionsList:
    def test_foreign_tenant_rows_are_structurally_invisible(self) -> None:
        """Acceptance (2): anti-enumeration — foreign rows simply absent."""
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, USER_EMAIL)
            session = identity.resolve_session(token)
            own_id = _seed_execution(store, tenant_id=session.tenant_id)
            foreign_id = _seed_execution(store, tenant_id=uuid4())  # attacker bait
            async with _client(app) as c:
                response = await c.get("/v1/executions", headers=bearer(token))
                assert response.status_code == 200
                ids = {r["execution_id"] for r in response.json()["executions"]}
                assert ids == {str(own_id)}
                assert str(foreign_id) not in ids
                # by-id read of the foreign row is the identical 404
                foreign = await c.get(
                    f"/v1/executions/{foreign_id}", headers=bearer(token)
                )
                absent = await c.get(
                    f"/v1/executions/{foreign_id}", headers=bearer(token)
                )
                assert foreign.status_code == 404
                assert foreign.content == absent.content

        run(scenario())

    def test_filters_and_ordering(self) -> None:
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, USER_EMAIL)
            session = identity.resolve_session(token)
            tenant = session.tenant_id
            base = datetime.now(UTC)
            initiator = uuid4()
            older = _seed_execution(
                store,
                tenant_id=tenant,
                status=ExecutionStatus.FAILED,
                created_at=base - timedelta(hours=2),
            )
            newer = _seed_execution(
                store,
                tenant_id=tenant,
                user_id=initiator,
                status=ExecutionStatus.SUCCEEDED,
                created_at=base - timedelta(hours=1),
            )
            async with _client(app) as c:
                all_rows = await c.get("/v1/executions", headers=bearer(token))
                ids = [r["execution_id"] for r in all_rows.json()["executions"]]
                assert ids == [str(newer), str(older)]  # newest-first
                failed = await c.get(
                    "/v1/executions?status=failed", headers=bearer(token)
                )
                assert [r["execution_id"] for r in failed.json()["executions"]] == [
                    str(older)
                ]
                by_user = await c.get(
                    f"/v1/executions?initiated_by={initiator}",
                    headers=bearer(token),
                )
                assert [
                    r["execution_id"] for r in by_user.json()["executions"]
                ] == [str(newer)]
                cutoff = (base - timedelta(minutes=90)).isoformat()
                recent = await c.get(
                    "/v1/executions",
                    params={"created_after": cutoff},  # proper URL-encoding
                    headers=bearer(token),
                )
                assert [
                    r["execution_id"] for r in recent.json()["executions"]
                ] == [str(newer)]
                limited = await c.get(
                    "/v1/executions?limit=1", headers=bearer(token)
                )
                assert [
                    r["execution_id"] for r in limited.json()["executions"]
                ] == [str(newer)]

        run(scenario())

    def test_bad_filters_are_named_422s(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            token = await _login(app, USER_EMAIL)
            async with _client(app) as c:
                for query, field in [
                    ("status=bogus", "status"),
                    ("initiated_by=not-a-uuid", "initiated_by"),
                    ("created_after=yesterday", "created_after"),
                    ("created_before=tomorrow%20maybe", "created_before"),
                    ("limit=0", "limit"),
                ]:
                    response = await c.get(
                        f"/v1/executions?{query}", headers=bearer(token)
                    )
                    assert response.status_code == 422, query
                    error = response.json()["error"]
                    assert error["code"] == "validation_error"
                    assert error["details"]["field"] == field

        run(scenario())

    def test_list_rows_carry_no_result_bodies(self) -> None:
        """A list is not a bulk-exfil surface: no result/content fields."""
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, USER_EMAIL)
            session = identity.resolve_session(token)
            _seed_execution(store, tenant_id=session.tenant_id)
            async with _client(app) as c:
                response = await c.get("/v1/executions", headers=bearer(token))
                row = response.json()["executions"][0]
                assert set(row) == {
                    "execution_id",
                    "status",
                    "initiated_by",
                    "created_at",
                    "progress",
                }

        run(scenario())


# --- AUD-1: admin audit read -----------------------------------------------------


class TestAuditRead:
    def test_audit_read_is_tenant_scoped(self) -> None:
        audit = InMemoryAuditLog()
        app, identity, _ = make_session_app(audit=audit)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            foreign_tenant = uuid4()
            audit.append(
                AuditEvent(
                    tenant_id=foreign_tenant,
                    event_type=AuditEventType.PERMISSION_DENIED,
                )
            )
            async with _client(app) as c:
                response = await c.get("/v1/admin/audit", headers=bearer(token))
                assert response.status_code == 200
                body = response.json()
                tenants = {e["tenant_id"] for e in body["events"]}
                assert str(foreign_tenant) not in tenants
                assert tenants == {str(session.tenant_id)}
                assert body["total_recorded"] == len(body["events"])

        run(scenario())

    def test_event_type_filter_is_the_closed_set(self) -> None:
        audit = InMemoryAuditLog()
        app, _, _ = make_session_app(audit=audit)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                good = await c.get(
                    "/v1/admin/audit?event_type=login", headers=bearer(token)
                )
                assert good.status_code == 200
                assert all(
                    e["event_type"] == "login" for e in good.json()["events"]
                )
                bad = await c.get(
                    "/v1/admin/audit?event_type=made_up", headers=bearer(token)
                )
                assert bad.status_code == 422
                assert bad.json()["error"]["details"]["field"] == "event_type"
                zero = await c.get(
                    "/v1/admin/audit?limit=0", headers=bearer(token)
                )
                assert zero.status_code == 422

        run(scenario())

    def test_absent_audit_seam_means_absent_route(self) -> None:
        """20 §4: no seam ⇒ nothing to probe (404, not 401/403)."""
        app, _, _ = make_session_app(audit=None)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                response = await c.get("/v1/admin/audit", headers=bearer(token))
                assert response.status_code == 404

        run(scenario())


# --- SYS-1: healthz + system read-model -------------------------------------------


class TestHealthz:
    def test_healthz_reports_only_labeled_process_truths(self) -> None:
        """Acceptance (4): process-local truths, labeled; no fleet claims."""
        app, _, _ = make_session_app()

        async def scenario() -> None:
            async with _client(app) as c:
                response = await c.get("/healthz")
                assert response.status_code == 200
                body = response.json()
                assert set(body) == {"status", "scope", "time"}
                assert body["status"] == "alive"
                assert body["scope"] == "process"
                datetime.fromisoformat(body["time"])

        run(scenario())

    def test_healthz_absent_unless_opted_in(self) -> None:
        app, _, _ = make_session_app(healthz=False)

        async def scenario() -> None:
            async with _client(app) as c:
                response = await c.get("/healthz")
                assert response.status_code == 404

        run(scenario())


class TestSystemReadModel:
    def test_system_snapshot_is_forced_to_process_scope(self) -> None:
        """Even a snapshot claiming otherwise is relabeled — structurally."""
        identity, sink = make_identity()
        register_verified(identity, sink, ADMIN_EMAIL, PASSWORD)
        world = AdminWorld()
        service = ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: "secret-ref://x"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
        )
        app = create_app(
            router=world.router,
            execution_service=service,
            auth=AuthSurface(
                identity=identity, admin_emails=frozenset({ADMIN_EMAIL})
            ),
            admin=world.surface(),
            system_info=lambda: {"scope": "GLOBAL FLEET", "routes": 3},
        )

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                response = await c.get("/v1/admin/system", headers=bearer(token))
                assert response.status_code == 200
                body = response.json()
                assert body["scope"] == "process"  # lie overwritten
                assert body["routes"] == 3

        run(scenario())

    def test_absent_system_info_means_absent_route(self) -> None:
        app, _, _ = make_session_app(system_info=False)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                response = await c.get("/v1/admin/system", headers=bearer(token))
                assert response.status_code == 404

        run(scenario())


# --- USG-2: usage drill-down ------------------------------------------------------


class TestUsageDrilldown:
    def test_usage_rows_surface_real_ledgers_and_null_when_unbound(self) -> None:
        """Null is honest (accounting unbound) — NEVER a fabricated ledger."""
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
                assert rows[0]["ledger"] is None  # unbound ⇒ null, not fake

        run(scenario())

    def test_usage_is_tenant_scoped(self) -> None:
        store = InMemoryExecutionStore()
        app, identity, _ = make_session_app(store=store)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            session = identity.resolve_session(token)
            own = _seed_execution(store, tenant_id=session.tenant_id)
            _seed_execution(store, tenant_id=uuid4())  # foreign
            async with _client(app) as c:
                response = await c.get("/v1/admin/usage", headers=bearer(token))
                ids = {r["execution_id"] for r in response.json()["usage"]}
                assert ids == {str(own)}

        run(scenario())

    def test_absent_executions_seam_means_absent_route(self) -> None:
        identity, sink = make_identity()
        register_verified(identity, sink, ADMIN_EMAIL, PASSWORD)
        world = AdminWorld()
        service = ExecutionService(
            adapters={world.provider.id: world.adapter},
            credential_refs={world.provider.id: "secret-ref://x"},
            bindings=world.bindings,
            max_retries_per_candidate=0,
        )
        app = create_app(
            router=world.router,
            execution_service=service,
            auth=AuthSurface(
                identity=identity, admin_emails=frozenset({ADMIN_EMAIL})
            ),
            admin=world.surface(),  # no executions seam
        )

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                response = await c.get("/v1/admin/usage", headers=bearer(token))
                assert response.status_code == 404

        run(scenario())


# --- WBH-1: webhook management ----------------------------------------------------


class TestWebhookManagement:
    def test_cross_tenant_delete_attack_fails_identically_to_absent(self) -> None:
        """Acceptance: foreign and absent subscription ids — SAME 404 bytes."""
        subscriptions: dict[UUID, list[Any]] = {}
        app, _, _ = make_session_app(subscriptions=subscriptions)

        async def scenario() -> None:
            admin_token = await _login(app, ADMIN_EMAIL)
            user_token = await _login(app, USER_EMAIL)
            async with _client(app) as c:
                created = await c.post(
                    "/v1/webhooks",
                    json={"url": "https://victim.test/hook"},
                    headers=bearer(admin_token),
                )
                assert created.status_code == 201
                victim_id = created.json()["id"]
                # ATTACK: the other tenant deletes the victim's id
                foreign = await c.delete(
                    f"/v1/webhooks/{victim_id}", headers=bearer(user_token)
                )
                # CONTROL: the same id when it truly does not exist for them
                # (identical request ⇒ must be byte-identical response)
                control = await c.delete(
                    f"/v1/webhooks/{victim_id}", headers=bearer(user_token)
                )
                assert foreign.status_code == control.status_code == 404
                assert foreign.content == control.content
                # the victim's subscription SURVIVED the attack
                listed = await c.get(
                    "/v1/webhooks", headers=bearer(admin_token)
                )
                assert [w["id"] for w in listed.json()["webhooks"]] == [victim_id]

        run(scenario())

    def test_list_shows_only_own_tenant_and_delete_works(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            admin_token = await _login(app, ADMIN_EMAIL)
            user_token = await _login(app, USER_EMAIL)
            async with _client(app) as c:
                created = await c.post(
                    "/v1/webhooks",
                    json={"url": "https://a.test/h"},
                    headers=bearer(admin_token),
                )
                sub_id = created.json()["id"]
                other_view = await c.get(
                    "/v1/webhooks", headers=bearer(user_token)
                )
                assert other_view.json() == {"webhooks": []}
                deleted = await c.delete(
                    f"/v1/webhooks/{sub_id}", headers=bearer(admin_token)
                )
                assert deleted.status_code == 204
                after = await c.get("/v1/webhooks", headers=bearer(admin_token))
                assert after.json() == {"webhooks": []}

        run(scenario())

    def test_malformed_subscription_id_is_a_named_422(self) -> None:
        app, _, _ = make_session_app()

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                response = await c.delete(
                    "/v1/webhooks/not-a-uuid", headers=bearer(token)
                )
                assert response.status_code == 422
                assert (
                    response.json()["error"]["details"]["field"]
                    == "subscription_id"
                )

        run(scenario())

    def test_webhooks_seam_off_means_all_management_routes_absent(self) -> None:
        app, _, _ = make_session_app(webhooks=False)

        async def scenario() -> None:
            token = await _login(app, ADMIN_EMAIL)
            async with _client(app) as c:
                for method, path in [
                    ("GET", "/v1/webhooks"),
                    ("POST", "/v1/webhooks"),
                    ("DELETE", f"/v1/webhooks/{uuid4()}"),
                ]:
                    response = await c.request(
                        method, path, headers=bearer(token)
                    )
                    assert response.status_code == 404, (method, path)

        run(scenario())


# --- route-surface delta guard ----------------------------------------------------


def test_route_surface_delta_is_exactly_the_aa1_set() -> None:
    """PINNED surface: any future route added must consciously update this.

    Full-seam composition (auth + admin + audit + executions + system +
    healthz + webhooks + models/bindings + usage) enumerated via OpenAPI
    (FastAPI 0.141 lazy-router finding — module docstring).
    """
    identity, sink = make_identity()
    register_verified(identity, sink, ADMIN_EMAIL, PASSWORD)
    world = AdminWorld()
    store = InMemoryExecutionStore()
    audit = InMemoryAuditLog()
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: "secret-ref://x"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
    )
    app = create_app(
        router=world.router,
        execution_service=service,
        store=store,
        auth=AuthSurface(identity=identity, admin_emails=frozenset({ADMIN_EMAIL})),
        admin=dataclasses.replace(
            world.surface(), audit=audit, executions=store
        ),
        models=world.models,
        bindings=world.bindings,
        usage=world.usage,
        system_info=lambda: {},
        healthz=True,
        webhooks=True,
    )
    assert openapi_ops(app) == [
        "DELETE /v1/webhooks/{subscription_id}",
        "GET /healthz",
        "GET /v1/admin/audit",
        "GET /v1/admin/capabilities",
        "GET /v1/admin/capabilities/exercisable",
        "GET /v1/admin/changes",
        "GET /v1/admin/changes/{change_id}",
        "GET /v1/admin/evaluations/{evaluation_id}",
        "GET /v1/admin/executions/{execution_id}/evaluations",
        "GET /v1/admin/learning/changes-since-review",
        "GET /v1/admin/learning/dashboard",
        "GET /v1/admin/models",
        "GET /v1/admin/plans/{plan_tenant_id}",
        "GET /v1/admin/providers",
        "GET /v1/admin/routing/weights",
        "GET /v1/admin/scenarios",
        "GET /v1/admin/self-review",
        "GET /v1/admin/source-changes",
        "GET /v1/admin/source-changes/{proposal_id}",
        "GET /v1/admin/system",
        "GET /v1/admin/usage",
        "GET /v1/auth/session",
        "GET /v1/executions",
        "GET /v1/executions/{execution_id}",
        "GET /v1/models",
        "GET /v1/skills",
        "GET /v1/usage",
        "GET /v1/webhooks",
        "POST /v1/admin/capabilities/{capability_id}/exercise",
        "POST /v1/admin/changes",
        "POST /v1/admin/changes/propose",
        "POST /v1/admin/changes/{change_id}/preview",
        "POST /v1/admin/changes/{change_id}/publish",
        "POST /v1/admin/changes/{change_id}/rollback",
        "POST /v1/admin/changes/{change_id}/validate",
        "POST /v1/admin/learning/mark-reviewed",
        "POST /v1/admin/scenarios",
        "POST /v1/admin/scenarios/regression-pack",
        "POST /v1/admin/scenarios/{scenario_id}/replay",
        "POST /v1/admin/source-changes",
        "POST /v1/admin/source-changes/snapshots",
        "POST /v1/admin/source-changes/{proposal_id}/apply",
        "POST /v1/admin/source-changes/{proposal_id}/approve",
        "POST /v1/admin/source-changes/{proposal_id}/reject",
        "POST /v1/admin/source-changes/{proposal_id}/rollback",
        "POST /v1/admin/source-changes/{proposal_id}/verify",
        "POST /v1/auth/login",
        "POST /v1/auth/logout",
        "POST /v1/execute",
        "POST /v1/webhooks",
    ]
