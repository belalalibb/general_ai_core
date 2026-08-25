"""Contract tests: identity/tenancy contract (03 §2 User/Tenant/Workspace/Project).

Verifies every closed set matches 03 §2 verbatim, the documented entity
shapes validate field-for-field, unknown fields/values are rejected
(deny-by-default), email_verified defaults to False, no secret-bearing
fields exist on any identity contract (20 §5), and instances are frozen
value objects with closed JSON Schema exports.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.identity import (
    Project,
    Tenant,
    TenantStatus,
    TenantType,
    User,
    UserStatus,
    Workspace,
)

# --- Closed sets exactly as written in 03 §2 ----------------------------------


def test_user_status_set_matches_spec() -> None:
    # 03 §2: active|disabled|pending
    assert {s.value for s in UserStatus} == {"active", "disabled", "pending"}


def test_tenant_type_set_matches_spec() -> None:
    # 03 §2: personal|organization
    assert {t.value for t in TenantType} == {"personal", "organization"}


def test_tenant_status_set_matches_spec() -> None:
    # 03 §2: active|suspended
    assert {s.value for s in TenantStatus} == {"active", "suspended"}


# --- Documented shapes validate ------------------------------------------------


def _user_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(uuid4()),
        "tenant_id": str(uuid4()),
        "email": "user@example.com",
        "email_verified": True,
        "preferred_language": "ar",
        "status": "active",
        "created_at": "2026-08-25T00:00:00Z",
        "updated_at": "2026-08-25T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_user_shape_validates_field_for_field() -> None:
    user = User.model_validate(_user_payload())
    assert user.email == "user@example.com"
    assert user.status is UserStatus.ACTIVE
    assert user.email_verified is True
    assert user.created_at.tzinfo is not None


def test_user_email_verified_defaults_false() -> None:
    # 41 §41: email verification is an explicit step — unverified by default.
    payload = _user_payload()
    del payload["email_verified"]
    assert User.model_validate(payload).email_verified is False


def test_tenant_shape_validates() -> None:
    tenant = Tenant.model_validate(
        {
            "id": str(uuid4()),
            "name": "Personal Tenant",
            "type": "personal",
            "status": "active",
            "plan_id": str(uuid4()),
        }
    )
    assert tenant.type is TenantType.PERSONAL
    assert tenant.status is TenantStatus.ACTIVE


def test_workspace_shape_validates() -> None:
    ws = Workspace.model_validate({"id": str(uuid4()), "tenant_id": str(uuid4()), "name": "Main"})
    assert ws.name == "Main"


def test_project_shape_validates_with_null_workspace() -> None:
    # 03 §2: workspace_id: uuid|null
    project = Project.model_validate(
        {
            "id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "workspace_id": None,
            "name": "Demo",
            "metadata": {"k": "v"},
        }
    )
    assert project.workspace_id is None
    assert project.metadata == {"k": "v"}


def test_project_workspace_id_accepts_uuid() -> None:
    ws_id = uuid4()
    project = Project.model_validate(
        {
            "id": str(uuid4()),
            "tenant_id": str(uuid4()),
            "workspace_id": str(ws_id),
            "name": "Demo",
            "metadata": {},
        }
    )
    assert project.workspace_id == ws_id


# --- Tenant scoping (20 §6) ------------------------------------------------------


def test_tenant_scoped_entities_carry_tenant_id() -> None:
    # 20 §6: every tenant-scoped entity must include tenant_id.
    for entity in (User, Workspace, Project):
        assert "tenant_id" in entity.model_fields, entity.__name__


def test_tenant_id_is_required_not_defaulted() -> None:
    with pytest.raises(ValidationError):
        Workspace.model_validate({"id": str(uuid4()), "name": "NoTenant"})


# --- No secret material in identity contracts (20 §5) ---------------------------


def test_no_secret_bearing_fields_on_identity_contracts() -> None:
    forbidden = {"password", "password_hash", "secret", "token", "api_key"}
    for entity in (User, Tenant, Workspace, Project):
        assert not (set(entity.model_fields) & forbidden), entity.__name__


# --- Invalid payloads rejected (deny-by-default) --------------------------------


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        User.model_validate(_user_payload(role="admin"))


def test_unknown_user_status_rejected() -> None:
    with pytest.raises(ValidationError):
        User.model_validate(_user_payload(status="banned"))


def test_unknown_tenant_type_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenant.model_validate(
            {
                "id": str(uuid4()),
                "name": "X",
                "type": "team",
                "status": "active",
                "plan_id": str(uuid4()),
            }
        )


def test_unknown_tenant_status_rejected() -> None:
    with pytest.raises(ValidationError):
        Tenant.model_validate(
            {
                "id": str(uuid4()),
                "name": "X",
                "type": "personal",
                "status": "archived",
                "plan_id": str(uuid4()),
            }
        )


def test_empty_email_rejected() -> None:
    with pytest.raises(ValidationError):
        User.model_validate(_user_payload(email=""))


def test_non_uuid_id_rejected() -> None:
    with pytest.raises(ValidationError):
        User.model_validate(_user_payload(id="not-a-uuid"))


# --- Value-object semantics ------------------------------------------------------


def test_identity_contracts_are_frozen() -> None:
    user = User.model_validate(_user_payload())
    with pytest.raises(ValidationError):
        user.email = "other@example.com"  # type: ignore[misc]


def test_json_schema_exports_are_closed() -> None:
    for entity in (User, Tenant, Workspace, Project):
        assert entity.model_json_schema()["additionalProperties"] is False
