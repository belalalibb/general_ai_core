"""P-B — runtime composition tests (Operator directive, Option A).

Hermetic: ``build_runtime_profile(environ={})`` composes the in-memory
profile — no env reads, no network, no database. Async requests driven
with ``asyncio.run`` (no pytest-asyncio for API tests; ADR-0001 note).

What must hold:

1. **No env vars ⇒ in-memory profile** — durable=False, no bridge/engine,
   the hermetic echo provider binds, a demo principal exists with budget.
2. **The whole loop works in-process**: healthz, sync execute (labeled
   echo output), async execute 202 → relay_once → run_once → poll shows
   the terminal record (the exact bodies main.py's tasks call).
3. **§14 stays gated**: the composed app's SourceChangeWorkflow has
   ``authoritative_applier=None`` regardless of profile.
4. **Env branches select durable bindings** (structure only, hermetic):
   with DATABASE_URL set the builder would go durable — proven via
   ``database_settings_from_env`` on the same dict the builder uses; the
   full durable path is exercised by the LIVE test below (env-gated).
5. **Real-provider branch**: GROQ_API_KEY/GSK_API_KEY in the injected
   environ bind ACTIVE domain rows for groq/genspark_llm with the
   verified model names — no network involved (adapters are constructed,
   never called).
6. **Lifespan hygiene**: create_runtime_app's lifespan starts/cancels
   the background tasks and the app still answers inside it.

LIVE (env-gated, manual): DATABASE_URL set ⇒ the durable profile builds
against real Postgres, seeds the default plan idempotently, and serves
register → console token → verify → login → execute with a granted
budget — the single-server VPS shape.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.composition.database import database_settings_from_env
from apps.composition.runtime import (
    DEFAULT_PLAN_NAME,
    ConsoleEmailSender,
    RuntimeProfile,
    build_runtime_profile,
)
from apps.main import create_runtime_app


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture()
def profile() -> RuntimeProfile:
    return build_runtime_profile(environ={})


# --- 1. the in-memory default profile --------------------------------------------


class TestInMemoryProfile:
    def test_no_env_means_in_memory(self, profile: RuntimeProfile) -> None:
        assert profile.durable is False
        assert profile.bridge is None
        assert profile.bindings is None

    def test_echo_provider_binds_when_no_keys(self, profile: RuntimeProfile) -> None:
        assert profile.provider_keys == ("local_echo",)
        entry = profile.providers.get("local_echo")
        assert entry.is_routable  # ACTIVE + functional ⇒ candidates exist

    def test_demo_principal_has_budget(self, profile: RuntimeProfile) -> None:
        principal = profile.demo_principal
        assert principal is not None
        summary = profile.usage.summary(principal.tenant_id)
        assert summary.plan == DEFAULT_PLAN_NAME

    def test_builder_reads_only_injected_environ(self) -> None:
        # The env dict is the ONLY input: an empty dict must win even if
        # the process env carried DATABASE_URL (hermetic guarantee).
        assert database_settings_from_env({}) is None

    def test_env_dict_selects_durable_branch(self) -> None:
        # Structure-only proof of the branch condition the builder uses.
        settings = database_settings_from_env({"DATABASE_URL": "postgresql+asyncpg://u:p@h/db"})
        assert settings is not None


# --- 2. the full in-process loop ---------------------------------------------------


class TestEndToEndLoop:
    def test_sync_execute_returns_labeled_echo(self, profile: RuntimeProfile) -> None:
        async def scenario() -> None:
            async with _client(profile.app) as client:
                response = await client.post("/v1/execute", json={"ask": "marhaba"})
            assert response.status_code == 200
            body = response.json()
            assert body["status"] == "succeeded"
            content = json.loads(body["result"]["content"])
            assert content["provider"] == "local-echo"
            assert content["echo"] == "marhaba"
            assert "no real model was called" in content["note"]

        run(scenario())

    def test_async_execute_drains_through_relay_and_worker(self, profile: RuntimeProfile) -> None:
        """202 → relay_once → run_once → terminal poll (main.py's bodies)."""

        async def scenario() -> None:
            async with _client(profile.app) as client:
                accepted = await client.post(
                    "/v1/execute",
                    json={"ask": "queued", "execution_policy": {"async": True}},
                )
                assert accepted.status_code == 202
                execution_id = accepted.json()["execution_id"]

                queued = await client.get(f"/v1/executions/{execution_id}")
                assert queued.json()["status"] == "queued"

                # The EXACT loop bodies apps/main.py schedules:
                assert await profile.relay.relay_once(max_records=16) == 1
                report = await profile.worker.run_once(max_messages=16)
                assert len(report.processed) == 1

                terminal = await client.get(f"/v1/executions/{execution_id}")
                assert terminal.json()["status"] == "succeeded"

        run(scenario())

    def test_healthz_serves(self, profile: RuntimeProfile) -> None:
        async def scenario() -> None:
            async with _client(profile.app) as client:
                response = await client.get("/healthz")
            assert response.status_code == 200
            assert response.json()["status"] == "alive"

        run(scenario())


# --- 3. §14 gate is profile-independent ---------------------------------------------


class TestSection14Gate:
    def test_workflow_composed_with_no_applier(self, profile: RuntimeProfile) -> None:
        workflow = profile.app.state.source_change_workflow
        assert workflow is not None
        assert workflow._authoritative_applier is None  # noqa: SLF001 — the gate itself


# --- 4. real-provider branch (hermetic — adapters built, never called) --------------


class TestRealProviderBranch:
    def test_groq_key_binds_active_groq(self) -> None:
        prof = build_runtime_profile(environ={"GROQ_API_KEY": "gsk-test-not-real"})
        assert prof.provider_keys == ("groq",)
        entry = prof.providers.get("groq")
        assert entry.is_routable  # domain ACTIVE (step 14) over disabled manifest
        model_keys = {m.model_key for m in prof.models.active_models()}
        assert "openai/gpt-oss-20b" in model_keys

    def test_both_keys_bind_both_providers(self) -> None:
        prof = build_runtime_profile(environ={"GROQ_API_KEY": "k1", "GSK_API_KEY": "k2"})
        assert set(prof.provider_keys) == {"groq", "genspark_llm"}
        # No echo fallback when real providers exist:
        assert "local_echo" not in prof.provider_keys

    def test_no_keys_falls_back_to_echo(self, profile: RuntimeProfile) -> None:
        assert profile.provider_keys == ("local_echo",)


# --- 5. console email binding (recorded decision 4) ----------------------------------


class TestConsoleEmailSender:
    def test_prints_labeled_json_with_token(self) -> None:
        stream = io.StringIO()
        ConsoleEmailSender(stream).send_verification("a@b.c", "tok-123")
        record = json.loads(stream.getvalue())
        assert record["email"] == "a@b.c"
        assert record["token"] == "tok-123"
        assert "forbidden" in record["delivery"]  # honest MVP label


# --- 6. lifespan hygiene --------------------------------------------------------------


class TestLifespan:
    def test_lifespan_starts_and_cancels_background_tasks(self) -> None:
        prof = build_runtime_profile(environ={})
        app = create_runtime_app(prof)

        async def scenario() -> None:
            async with app.router.lifespan_context(app):
                # Tasks are running on THIS loop; the API must serve.
                names = {t.get_name() for t in asyncio.all_tasks()}
                assert "outbox-relay" in names
                assert "exec-worker" in names
                async with _client(app) as client:
                    response = await client.post(
                        "/v1/execute",
                        json={"ask": "bg", "execution_policy": {"async": True}},
                    )
                    assert response.status_code == 202
                    execution_id = response.json()["execution_id"]
                    # The BACKGROUND tasks drain it — no manual run_once.
                    for _ in range(100):
                        await asyncio.sleep(0.05)
                        poll = await client.get(f"/v1/executions/{execution_id}")
                        if poll.json()["status"] in {"succeeded", "failed"}:
                            break
                    assert poll.json()["status"] == "succeeded"
            # After the context exits, both tasks are cancelled.
            names = {t.get_name() for t in asyncio.all_tasks()}
            assert "outbox-relay" not in names
            assert "exec-worker" not in names

        run(scenario())


# --- LIVE (env-gated): the durable single-server profile -----------------------------


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live durable-profile test runs manually only",
)
class TestLiveDurableProfile:
    def test_durable_profile_register_login_execute(self) -> None:
        environ = {"DATABASE_URL": os.environ["DATABASE_URL"]}
        stream = io.StringIO()
        prof = build_runtime_profile(environ=environ)
        assert prof.durable is True
        assert prof.bridge is not None
        assert prof.bindings is not None
        assert prof.demo_principal is None  # durable profile authenticates
        email = f"pb-live-{uuid4().hex[:8]}@example.com"
        password = "correct horse battery staple"  # noqa: S105 — test credential

        try:
            identity = prof.identity
            assert identity is not None
            # The durable rows hold only token DIGESTS (20 §5) — the ONLY
            # honest way to obtain the verification token is the console
            # delivery itself. ConsoleEmailSender resolves stdout lazily,
            # so redirect_stdout captures the delivery line.
            import contextlib

            with contextlib.redirect_stdout(stream):
                user = identity.register(email, password, "en")
            token = json.loads(stream.getvalue())["token"]
            identity.verify_email(token)
            session = identity.login(email, password)

            async def scenario() -> None:
                async with _client(prof.app) as client:
                    response = await client.post(
                        "/v1/execute",
                        json={"ask": "durable hello"},
                        headers={"Authorization": f"Bearer {session.token}"},
                    )
                assert response.status_code == 200
                assert response.json()["status"] == "succeeded"

            run(scenario())

            # Restart survival: a FRESH profile over the same database
            # resolves the SAME session (durable identity, P-A.2).
            prof2 = build_runtime_profile(environ=environ)
            try:
                identity2 = prof2.identity
                assert identity2 is not None
                resolved = identity2.get_user_for_session(session.token)
                assert resolved.id == user.id
            finally:
                _close(prof2)
        finally:
            _cleanup_tenant(prof, email)
            _close(prof)


def _close(prof: RuntimeProfile) -> None:
    if prof.bridge is not None and prof.bindings is not None:
        engine = prof.bindings.engine
        prof.bridge.run(engine.dispose())
        prof.bridge.close()


def _cleanup_tenant(prof: RuntimeProfile, email: str) -> None:
    """Delete the live test's rows (tenant cascade via explicit deletes)."""
    if prof.bindings is None or prof.bridge is None:
        return
    from sqlalchemy import text

    bindings = prof.bindings

    async def _delete() -> None:
        async with bindings.session_factory() as session:
            row = (
                await session.execute(
                    text("SELECT id, tenant_id FROM users WHERE email = :e"),
                    {"e": email},
                )
            ).first()
            if row is None:
                return
            user_id, tenant_id = row[0], row[1]
            # The live execute persisted durable execution rows (P-A.1) —
            # children first (execution_nodes FK is RESTRICT).
            await session.execute(
                text(
                    "DELETE FROM execution_nodes WHERE execution_id IN "
                    "(SELECT id FROM executions WHERE tenant_id = :t)"
                ),
                {"t": tenant_id},
            )
            await session.execute(
                text("DELETE FROM executions WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            await session.execute(
                text("DELETE FROM usage_ledger WHERE tenant_id = :t"),
                {"t": tenant_id},
            )
            await session.execute(
                text("DELETE FROM sessions WHERE user_id = :uid"), {"uid": user_id}
            )
            await session.execute(
                text("DELETE FROM user_credentials WHERE user_id = :uid"),
                {"uid": user_id},
            )
            await session.execute(
                text("DELETE FROM email_verification_tokens WHERE email = :e"),
                {"e": email},
            )
            await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
            await session.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": tenant_id})
            await session.commit()

    prof.bridge.run(_delete())
