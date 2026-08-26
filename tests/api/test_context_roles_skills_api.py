"""API surface semantics for Phase 6 slice 4 (T-IMPL-028; 41 §45; 10 §2/§7).

Hermetic — httpx ASGI transport, fake adapters, in-memory stores/registries;
no network, no server process (41 §49 posture carried).

Covers:

- GET /v1/skills (10 §7): selectable-only listing, exact row shape
  (manifest id, flat deduplicated requires_tools), empty registry => [].
- Role selection (10 §2 role object): admission by UUID and by unique
  name; unknown/ambiguous/non-selectable/scope-mismatch all deny as
  validation_error with named details; admitted role rides the payload.
- Conversation persistence: ask + assistant turns appended on success;
  failed executions keep the ask only; cross-user conversation denies
  unauthorized 403; unknown id auto-creates under the caller; idempotent
  replays do not duplicate turns.
- Context composition: composed 13 §5 object rides payload["context"]
  with history from PRIOR turns only; role objective is NOT duplicated
  as payload["role"] when the composer is present; budget failure maps
  to validation_error 422 with required/budget facts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI

from apps.api import InMemoryExecutionStore, Principal, create_app
from core.context.composer import ContextComposer
from core.contracts.base import utc_now
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.memory import MemoryItem, MemoryScope
from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.contracts.skills import (
    Skill,
    SkillManifest,
    SkillSource,
    SkillStatus,
    SkillToolRequirements,
    SkillType,
)
from core.execution.service import ExecutionService
from core.memory.memory import InMemoryConversationStore, InMemoryMemoryStore
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
from core.roles.registry import RoleRegistry, SkillRegistry
from core.routing.router import SimpleScoringRouter


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


# --- fakes (mirrors tests/api/test_execute_api.py posture) ---------------------------


def _provider_error() -> ProviderError:
    return ProviderError(
        category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
        retryable=False,
        safe_message="fake non_retryable_error",
        provider_code="RAW-INTERNAL-CODE",
    )


class FakeAdapter:
    """Scripted adapter: ProviderError => fail, dict => succeed with output."""

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.requests: list[ProviderGenerateRequest] = []

    def get_manifest(self) -> ProviderManifest:  # pragma: no cover - unused
        raise NotImplementedError

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        return CredentialHealth(
            credential_ref=credential_ref, status=CredentialStatus.ACTIVE
        )

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:  # pragma: no cover - unused
        return []

    async def get_capabilities(self) -> ProviderCapabilities:  # pragma: no cover
        return ProviderCapabilities()

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        self.requests.append(request)
        step: object = self.script.pop(0) if self.script else {"content": "answer"}
        if isinstance(step, ProviderError):
            return ProviderGenerateResponse(
                request_id=request.request_id,
                succeeded=False,
                error=step,
                latency_ms=7,
            )
        assert isinstance(step, dict)
        return ProviderGenerateResponse(
            request_id=request.request_id,
            succeeded=True,
            output=step,
            usage={"units": 1},
            latency_ms=5,
        )

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        raise NotImplementedError  # pragma: no cover - unused

    def normalize_error(self, error: object) -> ProviderError:
        return _provider_error()


def _manifest(provider_key: str) -> ProviderManifest:
    return ProviderManifest.model_validate(
        {
            "id": provider_key,
            "name": provider_key,
            "version": "1.0.0",
            "status": "active",
            "auth": {"types": ["api_key"], "supports_refresh": False},
            "account_pool": {"supported": False},
            "capabilities": {"chat": True},
            "operations": ["generate_text"],
            "models": {"discovery": "static", "static_models": []},
            "rate_limits": {"strategy": "provider_defined"},
            "health": {"checks": ["ping"]},
            "errors": {"mapping": "error_map.json"},
        }
    )


def _model(key: str) -> Model:
    return Model(
        id=uuid4(),
        model_key=key,
        display_name=key,
        tier=ModelTier.MEDIUM,
        modalities=["text"],
        capabilities=["reasoning"],
        quality_score=0.9,
        reliability_score=0.9,
        cost_score=0.9,
        speed_score=0.9,
        status=ModelStatus.ACTIVE,
    )


# --- domain fixtures ------------------------------------------------------------------


def make_role(
    *,
    name: str = "senior_software_architect",
    status: RoleStatus = RoleStatus.ACTIVE,
    scope: RoleScope = RoleScope.SYSTEM,
) -> Role:
    return Role(
        id=uuid4(),
        scope=scope,
        name=name,
        version="1.0.0",
        objective="Design and review software architecture.",
        status=status,
    )


def make_skill(
    *,
    manifest_id: str = "code_review",
    status: SkillStatus = SkillStatus.ACTIVE,
    source: SkillSource = SkillSource.LOCAL,
    required_tools: list[str] | None = None,
    optional_tools: list[str] | None = None,
) -> Skill:
    name = manifest_id
    manifest = SkillManifest(
        id=manifest_id,
        name=name,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=source,
        status=status,
        requires_tools=SkillToolRequirements(
            required=required_tools or [], optional=optional_tools or []
        ),
    )
    return Skill(
        id=uuid4(),
        name=name,
        version="1.0.0",
        type=SkillType.INSTRUCTION,
        source=source,
        manifest=manifest,
        status=status,
    )


class World:
    """One hermetic Phase 6 API world: all seams injected and shared."""

    def __init__(self, *, script: list[object] | None = None) -> None:
        self.providers = ProviderRegistry()
        self.models = ModelRegistry()
        self.bindings = BindingRegistry()
        self.principal = Principal(tenant_id=uuid4(), user_id=uuid4())
        self.store = InMemoryExecutionStore()
        self.skills = SkillRegistry()
        self.roles = RoleRegistry()
        self.conversations = InMemoryConversationStore()
        self.memory = InMemoryMemoryStore()

        self.provider = Provider(
            id=uuid4(),
            provider_key="prov_a",
            display_name="prov_a",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        self.providers.register(self.provider, _manifest("prov_a"))
        self.model = _model("model-alpha")
        self.models.register(self.model)
        self.bindings.register(
            ProviderModelBinding(
                provider_id=self.provider.id,
                model_id=self.model.id,
                provider_model_name="vendor/model-alpha",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        self.adapter = FakeAdapter(script)

    def app(self, *, with_composer: bool = False, context_budget: int = 16_000) -> FastAPI:
        router = SimpleScoringRouter(self.providers, self.models, self.bindings)
        service = ExecutionService(
            adapters={self.provider.id: self.adapter},
            credential_refs={self.provider.id: f"secret-ref://{self.provider.id}"},
            bindings=self.bindings,
            max_retries_per_candidate=0,
            sleeper=_no_sleep,
        )
        composer = (
            ContextComposer(self.memory, self.conversations, self.roles)
            if with_composer
            else None
        )
        return create_app(
            router=router,
            execution_service=service,
            store=self.store,
            principal=self.principal,
            skills=self.skills,
            roles=self.roles,
            conversations=self.conversations,
            composer=composer,
            context_budget=context_budget,
        )


async def _get(app: FastAPI, path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


async def _post(
    app: FastAPI, body: dict[str, Any], headers: dict[str, str] | None = None
) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/execute", json=body, headers=headers or {})


# --- GET /v1/skills (10 §7) -----------------------------------------------------------


def test_skills_empty_registry_lists_nothing() -> None:
    world = World()
    response = run(_get(world.app(), "/v1/skills"))
    assert response.status_code == 200
    assert response.json() == {"skills": []}


def test_skills_lists_selectable_rows_in_10_7_shape() -> None:
    world = World()
    world.skills.register(
        make_skill(manifest_id="code_review", required_tools=["github"])
    )
    response = run(_get(world.app(), "/v1/skills"))
    assert response.status_code == 200
    assert response.json() == {
        "skills": [
            {
                "id": "code_review",
                "version": "1.0.0",
                "status": "active",
                "requires_tools": ["github"],
            }
        ]
    }


def test_skills_listing_excludes_non_selectable_registrations() -> None:
    """Pipeline states, disabled, and imported-source skills are loaded
    but NEVER listed (loadable-not-selectable surfaced to the API)."""
    world = World()
    world.skills.register(make_skill(manifest_id="active_local"))
    world.skills.register(
        make_skill(manifest_id="still_reviewed", status=SkillStatus.REVIEWED)
    )
    world.skills.register(
        make_skill(manifest_id="switched_off", status=SkillStatus.DISABLED)
    )
    world.skills.register(
        make_skill(manifest_id="from_outside", source=SkillSource.IMPORTED)
    )
    response = run(_get(world.app(), "/v1/skills"))
    rows = response.json()["skills"]
    assert [row["id"] for row in rows] == ["active_local"]


def test_skills_tool_list_is_flat_and_deduplicated() -> None:
    world = World()
    world.skills.register(
        make_skill(
            manifest_id="tooling",
            required_tools=["github", "browser"],
            optional_tools=["browser", "search"],
        )
    )
    response = run(_get(world.app(), "/v1/skills"))
    assert response.json()["skills"][0]["requires_tools"] == [
        "github",
        "browser",
        "search",
    ]


# --- role selection (10 §2 role object) -----------------------------------------------


def test_role_admitted_by_unique_name_rides_payload() -> None:
    world = World()
    role = make_role()
    world.roles.register(role)
    body = {
        "ask": "design the system",
        "role": {"type": "system", "id": "senior_software_architect"},
    }
    response = run(_post(world.app(), body))
    assert response.status_code == 200
    sent = world.adapter.requests[0].payload
    assert sent["role"] == {"id": str(role.id), "objective": role.objective}


def test_role_admitted_by_registry_uuid() -> None:
    world = World()
    role = make_role()
    world.roles.register(role)
    body = {"ask": "design", "role": {"type": "system", "id": str(role.id)}}
    response = run(_post(world.app(), body))
    assert response.status_code == 200


def test_unknown_role_denies_validation_error() -> None:
    world = World()
    body = {"ask": "x", "role": {"type": "system", "id": "nonexistent"}}
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["field"] == "role.id"
    assert not world.adapter.requests  # denied BEFORE any provider work


def test_non_selectable_role_denies_with_named_status() -> None:
    world = World()
    world.roles.register(make_role(status=RoleStatus.DRAFT))
    body = {
        "ask": "x",
        "role": {"type": "system", "id": "senior_software_architect"},
    }
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    assert response.json()["error"]["details"]["role_status"] == "draft"


def test_ambiguous_role_name_denies_and_asks_for_id() -> None:
    world = World()
    world.roles.register(make_role(scope=RoleScope.SYSTEM))
    world.roles.register(make_role(scope=RoleScope.TENANT))
    body = {
        "ask": "x",
        "role": {"type": "system", "id": "senior_software_architect"},
    }
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    assert "Ambiguous" in response.json()["error"]["message"]


def test_role_type_scope_mismatch_denies() -> None:
    world = World()
    world.roles.register(make_role(scope=RoleScope.SYSTEM))
    body = {
        "ask": "x",
        "role": {"type": "tenant", "id": "senior_software_architect"},
    }
    response = run(_post(world.app(), body))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["details"] == {"field": "role.type", "expected": "system"}


# --- conversation persistence ---------------------------------------------------------


def test_success_appends_user_then_assistant_turn() -> None:
    world = World(script=[{"content": "the answer"}])
    conversation_id = uuid4()
    body = {"ask": "first question", "conversation_id": str(conversation_id)}
    response = run(_post(world.app(), body))
    assert response.status_code == 200
    history = world.conversations.get_history(
        world.principal.tenant_id, conversation_id
    )
    assert [(m.role.value, m.content) for m in history] == [
        ("user", "first question"),
        ("assistant", "the answer"),
    ]


def test_unknown_conversation_id_is_auto_created_under_caller() -> None:
    world = World()
    conversation_id = uuid4()
    run(_post(world.app(), {"ask": "hello", "conversation_id": str(conversation_id)}))
    conversation = world.conversations.get_conversation(
        world.principal.tenant_id, conversation_id
    )
    assert conversation.user_id == world.principal.user_id
    assert conversation.title == "hello"


def test_failed_execution_keeps_the_ask_only() -> None:
    world = World(script=[_provider_error()])
    conversation_id = uuid4()
    response = run(
        _post(world.app(), {"ask": "doomed", "conversation_id": str(conversation_id)})
    )
    assert response.status_code == 502
    history = world.conversations.get_history(
        world.principal.tenant_id, conversation_id
    )
    assert [(m.role.value, m.content) for m in history] == [("user", "doomed")]


def test_cross_user_conversation_denies_unauthorized() -> None:
    world = World()
    other_user_conversation = uuid4()
    from core.contracts.conversation import Conversation, ConversationStatus

    world.conversations.create_conversation(
        Conversation(
            id=other_user_conversation,
            tenant_id=world.principal.tenant_id,
            user_id=uuid4(),  # someone else in the SAME tenant
            title="not yours",
            status=ConversationStatus.ACTIVE,
        )
    )
    response = run(
        _post(
            world.app(),
            {"ask": "peek", "conversation_id": str(other_user_conversation)},
        )
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "unauthorized"
    # 13 §7: nothing was appended to the other user's history.
    history = world.conversations.get_history(
        world.principal.tenant_id, other_user_conversation
    )
    assert history == ()


def test_idempotent_replay_does_not_duplicate_turns() -> None:
    world = World()
    conversation_id = uuid4()
    app = world.app()
    body = {"ask": "once", "conversation_id": str(conversation_id)}
    headers = {"Idempotency-Key": "key-1"}
    first = run(_post(app, body, headers))
    second = run(_post(app, body, headers))
    assert first.json()["execution_id"] == second.json()["execution_id"]
    history = world.conversations.get_history(
        world.principal.tenant_id, conversation_id
    )
    assert len(history) == 2  # one user + one assistant turn, not four


# --- context composition (T-IMPL-027 wiring) -------------------------------------------


def test_composed_context_rides_payload_with_prior_history_only() -> None:
    world = World(script=[{"content": "turn-1"}, {"content": "turn-2"}])
    conversation_id = uuid4()
    app = world.app(with_composer=True)
    run(_post(app, {"ask": "first ask", "conversation_id": str(conversation_id)}))
    run(_post(app, {"ask": "second ask", "conversation_id": str(conversation_id)}))

    second_payload = world.adapter.requests[1].payload
    context = second_payload["context"]
    assert "role" not in second_payload  # never both context AND payload role
    blocks = context["context_blocks"]
    types = [block["type"] for block in blocks]
    assert types == ["history", "history", "ask"]
    # History = PRIOR turns only (composed before this ask was appended).
    assert blocks[0]["content"] == "user: first ask"
    assert blocks[1]["content"] == "assistant: turn-1"
    assert blocks[2]["content"] == "second ask"


def test_composed_context_includes_role_block_and_memory_preference() -> None:
    world = World()
    role = make_role()
    world.roles.register(role)
    world.memory.upsert(
        MemoryItem(
            id=uuid4(),
            tenant_id=world.principal.tenant_id,
            user_id=world.principal.user_id,
            scope=MemoryScope.TENANT,
            key="preferred_language",
            value="ar",
            source="user_settings",
            confidence=0.92,
            evidence_count=3,
            last_seen=utc_now(),
        )
    )
    app = world.app(with_composer=True)
    body = {
        "ask": "review this",
        "role": {"type": "system", "id": "senior_software_architect"},
    }
    response = run(_post(app, body))
    assert response.status_code == 200
    context = world.adapter.requests[0].payload["context"]
    types = [block["type"] for block in context["context_blocks"]]
    assert types == ["role", "preference", "ask"]
    role_block = context["context_blocks"][0]
    assert role_block["content"] == role.objective
    assert role_block["source"] == f"role:{role.id}"
    preference = context["context_blocks"][1]
    assert preference["content"] == 'preferred_language = "ar"'
    assert preference["confidence"] == 0.92


def test_context_exclusions_stay_named_data() -> None:
    world = World()
    low_confidence = MemoryItem(
        id=uuid4(),
        tenant_id=world.principal.tenant_id,
        user_id=world.principal.user_id,
        scope=MemoryScope.TENANT,
        key="maybe_preference",
        value="unsure",
        source="inference",
        confidence=0.2,
        evidence_count=1,
        last_seen=utc_now(),
    )
    world.memory.upsert(low_confidence)
    app = world.app(with_composer=True)
    run(_post(app, {"ask": "anything"}))
    context = world.adapter.requests[0].payload["context"]
    assert context["excluded"] == [
        {"reason": "low_confidence", "memory_id": str(low_confidence.id)}
    ]


def test_context_budget_exceeded_maps_to_validation_error() -> None:
    world = World()
    app = world.app(with_composer=True, context_budget=3)
    response = run(_post(app, {"ask": "this ask cannot fit"}))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"] == {"required": 19, "budget": 3}
    assert not world.adapter.requests  # denied before any provider work


def test_without_composer_role_rides_payload_and_no_context_block() -> None:
    world = World()
    world.roles.register(make_role())
    body = {
        "ask": "plain",
        "role": {"type": "system", "id": "senior_software_architect"},
    }
    run(_post(world.app(), body))
    payload = world.adapter.requests[0].payload
    assert "context" not in payload
    assert payload["role"]["objective"] == "Design and review software architecture."
