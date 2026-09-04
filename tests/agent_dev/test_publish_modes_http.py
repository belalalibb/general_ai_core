"""R169 A6 — GET /v1/dev/bindings/{binding_id}/publish-modes.

The list a UI dropdown binds to: every mode enumerated, selectability decided
by the binding's ``allowed_modes``, ``direct_push`` refused-by-default with a
machine-readable reason. Tenant-scoped; unknown and foreign ids are the same
404 (anti-enumeration).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from apps.agent_dev.git_tools import RepoBindingRegistry
from apps.agent_dev.http import DEV_ROUTER_PREFIX, create_dev_router
from core.contracts.publish_mode import (
    DEFAULT_ALLOWED_MODES,
    REASON_DIRECT_PUSH_NOT_ENABLED,
    REASON_MODE_NOT_IN_BINDING,
    PublishMode,
    PublishModesResponse,
)
from core.contracts.repo_binding import RepoBinding

TENANT = uuid4()
OTHER_TENANT = uuid4()
AUTH_HEADER = {"Authorization": "Bearer session-token"}


@dataclass(frozen=True)
class FakePrincipal:
    tenant_id: UUID


def _unauthenticated() -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "error": {
                "code": "unauthenticated",
                "message": "Authentication failed.",
                "retryable": False,
                "details": {},
                "trace_id": None,
            }
        },
    )


def _resolve(request: Request) -> FakePrincipal | JSONResponse:
    if request.headers.get("Authorization") != "Bearer session-token":
        return _unauthenticated()
    return FakePrincipal(tenant_id=TENANT)


def _binding(
    tmp_path: Path,
    *,
    tenant_id: UUID = TENANT,
    allowed: frozenset[PublishMode] | None = None,
) -> RepoBinding:
    root = tmp_path / f"repo_{uuid4().hex[:6]}"
    root.mkdir()
    payload: dict[str, object] = {
        "tenant_id": tenant_id,
        "remote_url": "https://github.com/example/repo.git",
        "branch": "main",
        "local_root": str(root),
        "credential_ref": "credref_test",
    }
    if allowed is not None:
        payload["allowed_modes"] = allowed
    return RepoBinding.model_validate(payload)


@dataclass
class World:
    client: TestClient
    bindings: RepoBindingRegistry
    default_binding: RepoBinding
    direct_push_binding: RepoBinding
    foreign_binding: RepoBinding


@pytest.fixture
def world(tmp_path: Path) -> World:
    registry = RepoBindingRegistry()
    default_binding = registry.register(_binding(tmp_path))
    direct_push_binding = registry.register(
        _binding(tmp_path, allowed=frozenset(DEFAULT_ALLOWED_MODES) | {PublishMode.DIRECT_PUSH})
    )
    foreign_binding = registry.register(_binding(tmp_path, tenant_id=OTHER_TENANT))
    app = FastAPI()
    app.include_router(create_dev_router(registry, resolve=_resolve))
    return World(
        client=TestClient(app),
        bindings=registry,
        default_binding=default_binding,
        direct_push_binding=direct_push_binding,
        foreign_binding=foreign_binding,
    )


def _url(binding_id: object) -> str:
    return f"{DEV_ROUTER_PREFIX}/bindings/{binding_id}/publish-modes"


class TestAdmission:
    def test_missing_bearer_is_401_before_lookup(self, world: World) -> None:
        response = world.client.get(_url(world.default_binding.id))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "unauthenticated"

    def test_unknown_binding_is_404_validation_error(self, world: World) -> None:
        missing = uuid4()
        response = world.client.get(_url(missing), headers=AUTH_HEADER)
        assert response.status_code == 404
        body = response.json()["error"]
        assert body["code"] == "validation_error"
        assert body["details"] == {"binding_id": str(missing)}

    def test_foreign_tenant_binding_is_identical_404(self, world: World) -> None:
        foreign = world.client.get(_url(world.foreign_binding.id), headers=AUTH_HEADER)
        missing = world.client.get(_url(uuid4()), headers=AUTH_HEADER)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json()["error"]["message"] == missing.json()["error"]["message"]
        assert foreign.json()["error"]["code"] == missing.json()["error"]["code"]

    def test_malformed_binding_id_is_404_not_500(self, world: World) -> None:
        response = world.client.get(_url("not-a-uuid"), headers=AUTH_HEADER)
        assert response.status_code == 404
        assert response.json()["error"]["details"] == {"binding_id": "not-a-uuid"}


class TestModes:
    def test_response_parses_as_contract(self, world: World) -> None:
        response = world.client.get(_url(world.default_binding.id), headers=AUTH_HEADER)
        assert response.status_code == 200
        parsed = PublishModesResponse.model_validate(response.json())
        assert parsed.binding_id == str(world.default_binding.id)
        assert parsed.default is PublishMode.PULL_REQUEST

    def test_every_mode_enumerated_in_enum_order(self, world: World) -> None:
        body = world.client.get(_url(world.default_binding.id), headers=AUTH_HEADER).json()
        assert [m["id"] for m in body["modes"]] == [m.value for m in PublishMode]
        for mode in body["modes"]:
            assert set(mode) == {"id", "label", "description", "selectable", "reason"}
            assert mode["label"] and mode["description"]

    def test_default_binding_refuses_direct_push_with_reason(self, world: World) -> None:
        body = world.client.get(_url(world.default_binding.id), headers=AUTH_HEADER).json()
        by_id = {m["id"]: m for m in body["modes"]}
        assert by_id["direct_push"]["selectable"] is False
        assert by_id["direct_push"]["reason"] == REASON_DIRECT_PUSH_NOT_ENABLED
        for mode_id in ("dry_run", "local_commit_only", "pull_request"):
            assert by_id[mode_id]["selectable"] is True
            assert by_id[mode_id]["reason"] is None

    def test_explicit_opt_in_makes_direct_push_selectable(self, world: World) -> None:
        body = world.client.get(_url(world.direct_push_binding.id), headers=AUTH_HEADER).json()
        by_id = {m["id"]: m for m in body["modes"]}
        assert by_id["direct_push"]["selectable"] is True
        assert by_id["direct_push"]["reason"] is None
        assert body["default"] == "pull_request"

    def test_restricted_binding_marks_missing_modes(self, world: World, tmp_path: Path) -> None:
        restricted = world.bindings.register(
            _binding(tmp_path, allowed=frozenset({PublishMode.DRY_RUN}))
        )
        body = world.client.get(_url(restricted.id), headers=AUTH_HEADER).json()
        by_id = {m["id"]: m for m in body["modes"]}
        assert by_id["dry_run"]["selectable"] is True
        assert by_id["pull_request"]["selectable"] is False
        assert by_id["pull_request"]["reason"] == REASON_MODE_NOT_IN_BINDING
        assert by_id["direct_push"]["reason"] == REASON_DIRECT_PUSH_NOT_ENABLED

    def test_response_never_carries_credential_or_remote(self, world: World) -> None:
        text = world.client.get(_url(world.default_binding.id), headers=AUTH_HEADER).text
        assert "credref_" not in text
        assert "github.com" not in text
        assert world.default_binding.local_root not in text
