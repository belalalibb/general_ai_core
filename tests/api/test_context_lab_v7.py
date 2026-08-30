"""V7 chunk 4 — Context Validation Lab (dry-run over the REAL composer).

Hermetic — httpx ASGI transport against the composed FastAPI app; live
in-memory registries only, no network. Async requests driven with
asyncio.run (no pytest-asyncio; ADR-0001).

Covers the frozen-roadmap clause "Context Validation Lab" plus "Agent
gains the corresponding tools":

- CLOSED CHECK SET: the lab grades exactly LAB_CHECK_NAMES — each a
  13 §5/§10 composer promise verified over the ACTUAL composition
  (determinism proven by composing twice), never invented strings.
- REAL DRY-RUN: the lab composes with the SAME composer instance the
  execute path composes with (one composer, two consumers) — blocks,
  named exclusions, and verdicts are data; nothing executes, nothing is
  billed, nothing is written (asserted: memory/history untouched).
- HONEST FAILURES (P6): impossible budget and refused roles are
  validated:False DATA carrying the named facts, never transport 500s.
- 13 §7 / 20 §6: absent, foreign-tenant AND foreign-user conversation
  ids answer identically (404 over HTTP; honest error via the tool).
- GATES: non-admin 403 unauthorized on both routes; absent composer =
  absent lab = absent routes/tools (20 §4).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.admin_agent.contracts import ToolClass
from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.tools import AgentToolSurface, build_registry
from apps.api import create_app
from apps.api.context_lab import LAB_CHECK_NAMES, ContextLabService
from apps.api.store import InMemoryExecutionStore
from core.context.composer import ContextComposer
from core.contracts.base import utc_now
from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import MemoryItem, MemoryScope
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryConversationStore, InMemoryMemoryStore
from core.roles.registry import RoleRegistry
from tests.api.test_admin_api import World, _no_sleep

ALL_LAB_CHECKS = sorted(LAB_CHECK_NAMES)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def _get(app: FastAPI, path: str) -> httpx.Response:
    async with _client(app) as client:
        return await client.get(path)


async def _post(
    app: FastAPI, path: str, body: dict[str, object] | None = None
) -> httpx.Response:
    async with _client(app) as client:
        return await client.post(path, json=body)


class LabWorld:
    """Admin World + the context seams the lab needs, one composition."""

    def __init__(self, *, is_admin: bool = True) -> None:
        self.world = World(is_admin=is_admin)
        self.memory = InMemoryMemoryStore()
        self.conversations = InMemoryConversationStore()
        self.roles = RoleRegistry()
        self.composer = ContextComposer(self.memory, self.conversations, self.roles)

    @property
    def principal(self) -> Any:
        return self.world.principal

    def app(self, *, with_composer: bool = True, with_admin: bool = True) -> FastAPI:
        world = self.world
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
            admin=world.surface() if with_admin else None,
            roles=self.roles,
            conversations=self.conversations,
            composer=self.composer if with_composer else None,
        )

    def add_role(self, *, status: RoleStatus = RoleStatus.ACTIVE) -> Role:
        role = Role(
            id=uuid4(),
            scope=RoleScope.SYSTEM,
            name="architect",
            version="1.0.0",
            objective="Design and review software architecture.",
            status=status,
        )
        self.roles.register(role)
        return role

    def add_memory(
        self, *, key: str = "preferred_language", confidence: float = 0.92
    ) -> MemoryItem:
        item = MemoryItem(
            id=uuid4(),
            tenant_id=self.principal.tenant_id,
            user_id=self.principal.user_id,
            scope=MemoryScope.TENANT,
            key=key,
            value="ar",
            source="user_settings",
            confidence=confidence,
            evidence_count=3,
            last_seen=utc_now(),
        )
        self.memory.upsert(item)
        return item

    def add_conversation(self, *, user_id: UUID | None = None) -> Conversation:
        conversation = Conversation(
            id=uuid4(),
            tenant_id=self.principal.tenant_id,
            user_id=user_id if user_id is not None else self.principal.user_id,
            title="lab",
            status=ConversationStatus.ACTIVE,
        )
        self.conversations.create_conversation(conversation)
        self.conversations.append_message(
            self.principal.tenant_id,
            Message(
                id=uuid4(),
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content="earlier turn",
                created_at=utc_now(),
            ),
        )
        return conversation


# --- module ------------------------------------------------------------------------


class TestLabModule:
    def test_checks_is_the_closed_sorted_set(self) -> None:
        lab = LabWorld()
        service = ContextLabService(composer=lab.composer)
        assert service.checks() == ALL_LAB_CHECKS
        assert service.checks() == sorted(LAB_CHECK_NAMES)


# --- HTTP surface ------------------------------------------------------------------


class TestLabRoutes:
    def test_checks_route_lists_the_closed_set(self) -> None:
        lab = LabWorld()
        response = run(_get(lab.app(), "/v1/admin/context-lab/checks"))
        assert response.status_code == 200
        assert response.json() == {"checks": ALL_LAB_CHECKS}

    def test_validate_composes_for_real_and_grades(self) -> None:
        lab = LabWorld()
        role = lab.add_role()
        item = lab.add_memory()
        response = run(
            _post(
                lab.app(),
                "/v1/admin/context-lab/validate",
                {"ask": "review this design", "role_id": str(role.id)},
            )
        )
        assert response.status_code == 200
        body = response.json()
        assert body["validated"] is True
        assert body["passed"] is True
        assert [row["name"] for row in body["checks"]] == ALL_LAB_CHECKS
        assert all(row["passed"] for row in body["checks"])
        blocks = body["context"]["context_blocks"]
        # The REAL composer's deterministic order: role, memory, ask last.
        assert blocks[0]["type"] == "role"
        assert blocks[0]["source"] == f"role:{role.id}"
        assert blocks[-1]["type"] == "ask"
        assert any(b["source"] == f"memory:{item.id}" for b in blocks)

    def test_exclusions_ride_as_named_data(self) -> None:
        lab = LabWorld()
        low = lab.add_memory(key="maybe", confidence=0.2)  # below 0.5 floor
        body = run(
            _post(
                lab.app(),
                "/v1/admin/context-lab/validate",
                {"ask": "hello"},
            )
        ).json()
        assert body["validated"] is True
        excluded = body["context"]["excluded"]
        assert {"reason": "low_confidence", "memory_id": str(low.id)} in excluded
        # exclusions_named still passes: the reason IS in the closed set.
        assert body["passed"] is True

    def test_impossible_budget_is_honest_data_not_a_500(self) -> None:
        lab = LabWorld()
        response = run(
            _post(
                lab.app(),
                "/v1/admin/context-lab/validate",
                {"ask": "x" * 100, "context_budget": 10},
            )
        )
        assert response.status_code == 200
        body = response.json()
        assert body["validated"] is False
        assert body["required"] == 100
        assert body["budget"] == 10
        assert "budget" in body["error"]

    def test_refused_role_is_honest_data(self) -> None:
        lab = LabWorld()
        draft = lab.add_role(status=RoleStatus.DRAFT)
        for role_id, needle in ((uuid4(), "unknown role id"), (draft.id, "not")):
            body = run(
                _post(
                    lab.app(),
                    "/v1/admin/context-lab/validate",
                    {"ask": "hello", "role_id": str(role_id)},
                )
            ).json()
            assert body["validated"] is False, role_id
            assert needle in body["error"]

    def test_lab_reads_but_never_writes(self) -> None:
        lab = LabWorld()
        conversation = lab.add_conversation()
        lab.add_memory()
        before_history = lab.conversations.get_history(
            lab.principal.tenant_id, conversation.id
        )
        body = run(
            _post(
                lab.app(),
                "/v1/admin/context-lab/validate",
                {"ask": "hello", "conversation_id": str(conversation.id)},
            )
        ).json()
        assert body["validated"] is True
        # History composed as a block, but NOTHING was appended (dry-run).
        assert any(
            b["type"] == "history" for b in body["context"]["context_blocks"]
        )
        after_history = lab.conversations.get_history(
            lab.principal.tenant_id, conversation.id
        )
        assert after_history == before_history

    def test_unadmitted_conversation_ids_answer_identically(self) -> None:
        lab = LabWorld()
        foreign_user = lab.add_conversation(user_id=uuid4())  # same tenant
        for conversation_id in (uuid4(), foreign_user.id):
            response = run(
                _post(
                    lab.app(),
                    "/v1/admin/context-lab/validate",
                    {"ask": "peek", "conversation_id": str(conversation_id)},
                )
            )
            assert response.status_code == 404, conversation_id
            body = response.json()
            assert set(body.keys()) == {"error"}
            assert body["error"]["code"] == "validation_error"

    def test_non_admin_denied_on_both_routes(self) -> None:
        lab = LabWorld(is_admin=False)
        app = lab.app()
        for response in (
            run(_get(app, "/v1/admin/context-lab/checks")),
            run(
                _post(app, "/v1/admin/context-lab/validate", {"ask": "hello"})
            ),
        ):
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "unauthorized"

    def test_absent_composer_means_no_lab_routes(self) -> None:
        lab = LabWorld()
        app = lab.app(with_composer=False)
        assert (
            run(_get(app, "/v1/admin/context-lab/checks")).status_code == 404
        )
        assert (
            run(
                _post(app, "/v1/admin/context-lab/validate", {"ask": "x"})
            ).status_code
            == 404
        )

    def test_absent_admin_surface_means_no_lab_routes(self) -> None:
        lab = LabWorld()
        app = lab.app(with_admin=False)
        assert (
            run(_get(app, "/v1/admin/context-lab/checks")).status_code == 404
        )


# --- agent tools -------------------------------------------------------------------


def _agent_surface(
    lab: LabWorld, service: ContextLabService | None
) -> AgentToolSurface:
    world = lab.world
    execution_service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return AgentToolSurface(
        providers=world.providers,
        models=world.models,
        router=world.router,
        execution_service=execution_service,
        execution_store=InMemoryExecutionStore(),
        admin=world.surface(),
        usage=world.usage,
        audit=world.audit,
        context_lab=service,
    )


class TestAgentLabTools:
    def test_tools_registered_as_r0(self) -> None:
        # The lab is a dry-run READ: composes for real, executes nothing,
        # bills nothing, writes nothing — both tools are R0 (recorded).
        lab = LabWorld()
        service = lab.app().state.context_lab_service
        registry = build_registry(_agent_surface(lab, service))
        checks_spec = registry.get("list_lab_checks")
        validate_spec = registry.get("validate_context")
        assert checks_spec is not None
        assert checks_spec.tool_class is ToolClass.R0_READ
        assert validate_spec is not None
        assert validate_spec.tool_class is ToolClass.R0_READ
        assert validate_spec.allowed_args == frozenset(
            {"ask", "role_id", "conversation_id", "context_budget"}
        )

    def test_agent_checks_match_the_route(self) -> None:
        lab = LabWorld()
        app = lab.app()
        registry = build_registry(_agent_surface(lab, app.state.context_lab_service))
        dispatcher = ToolDispatcher(registry, audit=lab.world.audit)
        record = run(dispatcher.dispatch(lab.principal, "list_lab_checks", {}))
        assert record.ok
        route_body = run(_get(app, "/v1/admin/context-lab/checks")).json()
        assert record.result == route_body

    def test_agent_validate_runs_the_same_lab(self) -> None:
        lab = LabWorld()
        role = lab.add_role()
        app = lab.app()
        registry = build_registry(_agent_surface(lab, app.state.context_lab_service))
        dispatcher = ToolDispatcher(registry, audit=lab.world.audit)
        record = run(
            dispatcher.dispatch(
                lab.principal,
                "validate_context",
                {"ask": "review this", "role_id": str(role.id)},
            )
        )
        assert record.ok, record.refusal
        assert record.result is not None
        assert record.result["validated"] is True
        assert record.result["passed"] is True

    def test_agent_refusals_are_honest_content(self) -> None:
        lab = LabWorld()
        service = lab.app().state.context_lab_service
        registry = build_registry(_agent_surface(lab, service))
        dispatcher = ToolDispatcher(registry, audit=lab.world.audit)
        # Missing ask.
        record = run(
            dispatcher.dispatch(lab.principal, "validate_context", {"ask": ""})
        )
        assert record.ok and record.result == {"error": "ask is required"}
        # Malformed role id — pydantic's named refusal as content.
        record = run(
            dispatcher.dispatch(
                lab.principal,
                "validate_context",
                {"ask": "x", "role_id": "not-a-uuid"},
            )
        )
        assert record.ok
        assert record.result is not None
        error = record.result["error"]
        assert isinstance(error, str) and error.startswith("invalid lab request")
        # Unadmitted conversation — anti-enumeration.
        record = run(
            dispatcher.dispatch(
                lab.principal,
                "validate_context",
                {"ask": "x", "conversation_id": str(uuid4())},
            )
        )
        assert record.ok
        assert record.result == {"error": "unknown conversation id"}

    def test_absent_lab_field_means_absent_tools(self) -> None:
        lab = LabWorld()
        registry = build_registry(_agent_surface(lab, None))
        assert "list_lab_checks" not in registry.names()
        assert "validate_context" not in registry.names()

    def test_non_admin_dispatch_refused(self) -> None:
        lab = LabWorld()
        service = lab.app().state.context_lab_service
        registry = build_registry(_agent_surface(lab, service))
        dispatcher = ToolDispatcher(registry, audit=lab.world.audit)
        non_admin = dataclasses.replace(lab.principal, is_admin=False)
        for name, args in (
            ("list_lab_checks", {}),
            ("validate_context", {"ask": "x"}),
        ):
            record = run(dispatcher.dispatch(non_admin, name, dict(args)))
            assert not record.ok, name
            assert record.refusal == "admin access required"
