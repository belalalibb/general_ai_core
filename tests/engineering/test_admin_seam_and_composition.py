"""Admin seam (/v1/admin/engineering/*) + composition guard (ADR-0012 §4, ADR-0009 §14).

Admin ISSUES tickets and GRANTS permissions on the SAME firewall/ledger the
runtime consumes; a non-admin principal is denied; an absent
AGENT_WORKSPACE_ROOT ⇒ absent routes; the platform's own checkout is refused.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from apps.api.engineering_admin import EngineeringAdminSurface
from apps.composition.engineering import (
    ENV_WORKSPACE_COMMANDS,
    ENV_WORKSPACE_ROOT,
    PLATFORM_ROOT,
    WorkspaceRootRefused,
    build_engineering,
    grant_engineering_reads,
    grant_engineering_writes,
    workspace_root_refusal,
)
from core.audit.memory import InMemoryAuditLog
from core.contracts.engineering import EngineeringAct
from core.engineering.tools import (
    ENGINEERING_READ_PERMISSIONS,
    WORKSPACE_EXEC,
    WORKSPACE_WRITE,
)
from core.security.firewall import CapabilityFirewall, TenantPolicy
from tests.api.test_admin_api import World


def _engineering(tmp_path: Path, audit: InMemoryAuditLog) -> Any:
    env = {ENV_WORKSPACE_ROOT: str(tmp_path), ENV_WORKSPACE_COMMANDS: "python3, pytest"}
    composed = build_engineering(env, audit=audit)
    assert composed is not None
    return composed


def _admin_surface(world: World, tmp_path: Path) -> EngineeringAdminSurface:
    composed = _engineering(tmp_path, world.audit)
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(
        world.principal.tenant_id,
        TenantPolicy(
            granted_permissions=frozenset({"source.read"}),
            granted_entitlements=frozenset({"agent.tools"}),
        ),
    )
    return EngineeringAdminSurface(
        bundle=composed.bundle,
        firewall=firewall,
        remote=composed.remote,
        commands=composed.commands,
        grant_writes=grant_engineering_writes,
    )


def _app(world: World, engineering: EngineeringAdminSurface | None) -> FastAPI:
    from apps.api.app import create_app
    from core.execution.service import ExecutionService

    async def _no_sleep(_: float) -> None:
        return None

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
        admin=world.surface(),
        engineering_admin=engineering,
    )


def _call(app: FastAPI, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    async def go() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, json=body)

    return asyncio.run(go())


class TestAdminSeam:
    def test_status_issue_list_revoke_grant(self, tmp_path: Path) -> None:
        world = World(is_admin=True)
        surface = _admin_surface(world, tmp_path)
        app = _app(world, surface)

        status = _call(app, "GET", "/v1/admin/engineering/status")
        assert status.status_code == 200
        body = status.json()
        assert body["configured"] is True
        assert body["commands"] == ["python3", "pytest"]
        assert body["tenant_granted"] == ["source.read"]
        assert body["authorizations"] == []

        issued = _call(
            app,
            "POST",
            "/v1/admin/engineering/authorizations",
            {"acts": ["fs.write", "cmd.run"], "uses": 3, "ttl_minutes": 30, "note": "bench"},
        )
        assert issued.status_code == 201
        ticket = issued.json()
        assert ticket["uses_remaining"] == 3 and sorted(ticket["acts"]) == ["cmd.run", "fs.write"]
        assert ticket["tenant_id"] == str(world.principal.tenant_id)

        listed = _call(app, "GET", "/v1/admin/engineering/authorizations").json()
        assert [t["id"] for t in listed["authorizations"]] == [ticket["id"]]

        # The SAME ledger the runtime consumes sees the ticket.
        burned = surface.bundle.ledger.consume_ticket(
            authorization_id=UUID(ticket["id"]),
            workspace=surface.bundle.workspace_label,
            act=EngineeringAct.FS_WRITE,
        )
        assert burned.uses_remaining == 2

        revoked = _call(app, "POST", f"/v1/admin/engineering/authorizations/{ticket['id']}/revoke")
        assert revoked.status_code == 200 and revoked.json()["revoked"] is True

        granted = _call(
            app,
            "POST",
            "/v1/admin/engineering/grants",
            {"tenant_id": str(world.principal.tenant_id), "permissions": [WORKSPACE_WRITE]},
        )
        assert granted.status_code == 200
        assert WORKSPACE_WRITE in granted.json()["granted_permissions"]
        policy = surface.firewall.policy_for(world.principal.tenant_id)
        assert policy is not None and WORKSPACE_WRITE in policy.granted_permissions
        assert WORKSPACE_EXEC not in policy.granted_permissions

    def test_unknown_permission_and_bad_uuid_are_422(self, tmp_path: Path) -> None:
        world = World(is_admin=True)
        app = _app(world, _admin_surface(world, tmp_path))
        bad = _call(
            app,
            "POST",
            "/v1/admin/engineering/grants",
            {"tenant_id": str(world.principal.tenant_id), "permissions": ["source.read"]},
        )
        assert bad.status_code == 422
        unknown_tenant = _call(
            app,
            "POST",
            "/v1/admin/engineering/grants",
            {"tenant_id": str(uuid4()), "permissions": [WORKSPACE_WRITE]},
        )
        assert unknown_tenant.status_code == 422
        revoke = _call(app, "POST", "/v1/admin/engineering/authorizations/not-a-uuid/revoke")
        assert revoke.status_code in {400, 422}

    def test_non_admin_is_denied(self, tmp_path: Path) -> None:
        world = World(is_admin=False)
        app = _app(world, _admin_surface(world, tmp_path))
        assert _call(app, "GET", "/v1/admin/engineering/status").status_code in {401, 403}
        assert _call(
            app, "POST", "/v1/admin/engineering/authorizations", {"acts": ["fs.write"]}
        ).status_code in {401, 403}

    def test_absent_configuration_means_absent_routes(self) -> None:
        world = World(is_admin=True)
        app = _app(world, None)
        assert _call(app, "GET", "/v1/admin/engineering/status").status_code == 404


class TestCompositionGuard:
    def test_absent_or_invalid_root_is_none(self, tmp_path: Path) -> None:
        audit = InMemoryAuditLog()
        assert build_engineering({}, audit=audit) is None
        assert build_engineering({ENV_WORKSPACE_ROOT: "   "}, audit=audit) is None
        assert build_engineering({ENV_WORKSPACE_ROOT: str(tmp_path / "nope")}, audit=audit) is None

    def test_platform_checkout_is_refused(self) -> None:
        audit = InMemoryAuditLog()
        with pytest.raises(WorkspaceRootRefused):
            build_engineering({ENV_WORKSPACE_ROOT: str(PLATFORM_ROOT)}, audit=audit)
        with pytest.raises(WorkspaceRootRefused):
            build_engineering({ENV_WORKSPACE_ROOT: str(PLATFORM_ROOT / "core")}, audit=audit)
        with pytest.raises(WorkspaceRootRefused):
            build_engineering({ENV_WORKSPACE_ROOT: str(PLATFORM_ROOT.parent)}, audit=audit)

    def test_guard_is_pure_data(self, tmp_path: Path) -> None:
        assert workspace_root_refusal(tmp_path / "ws", platform_root=tmp_path / "platform") is None
        assert workspace_root_refusal(tmp_path / "p" / "x", platform_root=tmp_path / "p")
        assert workspace_root_refusal(tmp_path, platform_root=tmp_path)

    def test_reads_granted_on_admission_writes_never_implicitly(self) -> None:
        firewall = CapabilityFirewall()
        tenant = uuid4()
        grant_engineering_reads(firewall, tenant)  # no policy → no-op
        assert firewall.policy_for(tenant) is None
        firewall.set_tenant_policy(
            tenant,
            TenantPolicy(
                granted_permissions=frozenset({"source.read"}),
                granted_entitlements=frozenset({"agent.tools"}),
            ),
        )
        grant_engineering_reads(firewall, tenant)
        policy = firewall.policy_for(tenant)
        assert policy is not None
        assert ENGINEERING_READ_PERMISSIONS <= policy.granted_permissions
        assert WORKSPACE_WRITE not in policy.granted_permissions
