"""R167-A D-09: an admin write-permission grant to ANY tenant must leave an audit row.

Fail-first evidence lives in ``evidence/fixes/D-09.md``. The grant route mutates
another tenant's firewall policy; 20 §9 lists ``security_policy_changed`` as a
must-audit event, and before this round nothing emitted it.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from core.contracts.audit import AuditEventType
from core.engineering.tools import WORKSPACE_WRITE
from core.security.firewall import TenantPolicy
from tests.api.test_admin_api import World
from tests.engineering.test_admin_seam_and_composition import _admin_surface, _app, _call


def test_grant_to_foreign_tenant_is_audited_with_actor_target_and_outcome(tmp_path: Path) -> None:
    world = World(is_admin=True)
    surface = _admin_surface(world, tmp_path)
    target_tenant = uuid4()
    surface.firewall.set_tenant_policy(
        target_tenant,
        TenantPolicy(
            granted_permissions=frozenset({"source.read"}), granted_entitlements=frozenset()
        ),
    )
    app = _app(world, surface)
    before = world.audit.count(target_tenant)

    granted = _call(
        app,
        "POST",
        "/v1/admin/engineering/grants",
        {"tenant_id": str(target_tenant), "permissions": [WORKSPACE_WRITE]},
    )
    assert granted.status_code == 200

    rows = world.audit.read(target_tenant, event_type=AuditEventType.SECURITY_POLICY_CHANGED)
    assert world.audit.count(target_tenant) == before + 1
    assert len(rows) == 1
    row = rows[0]
    assert row.tenant_id == target_tenant  # target, not the admin's own tenant
    assert row.actor_id == world.principal.user_id  # who
    assert row.details["surface"] == "engineering_grant"
    assert row.details["actor_tenant_id"] == str(world.principal.tenant_id)
    assert row.details["permissions"] == [WORKSPACE_WRITE]
    assert WORKSPACE_WRITE in row.details["granted_permissions"]
    assert row.details["outcome"] == "granted"


def test_refused_grant_is_not_recorded_as_a_policy_change(tmp_path: Path) -> None:
    world = World(is_admin=True)
    surface = _admin_surface(world, tmp_path)
    app = _app(world, surface)
    bad = _call(
        app,
        "POST",
        "/v1/admin/engineering/grants",
        {"tenant_id": str(world.principal.tenant_id), "permissions": ["source.read"]},
    )
    assert bad.status_code == 422
    rows = world.audit.read(
        world.principal.tenant_id, event_type=AuditEventType.SECURITY_POLICY_CHANGED
    )
    assert len(rows) == 0
