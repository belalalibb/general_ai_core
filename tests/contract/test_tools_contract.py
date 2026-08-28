"""Contract tests: Tool entity + tool manifest (FINAL Phase 1 gap-fix).

Authority: 03 §6 (Tool entity, field-for-field), 03 §8 (firewall rule),
14 §4 (manifest shape), §5 (locations), §7 (firewall check list),
§11 (provider-agent tool classification), 41 §17 (field list).
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.tools import (
    DEFAULT_APPROVAL_REQUIREMENT,
    DEFAULT_PROVIDER_AGENT_TOOL_CLASS,
    FIREWALL_CHECK_ORDER,
    ApprovalRequirement,
    ProviderAgentToolClass,
    Tool,
    ToolCredentialsSpec,
    ToolLocation,
    ToolManifest,
    ToolStatus,
)

# --- Closed sets (verbatim from spec) ----------------------------------------------


def test_tool_location_closed_set_verbatim() -> None:
    """03 §6 / 14 §5: server|client|hybrid."""
    assert {loc.value for loc in ToolLocation} == {"server", "client", "hybrid"}


def test_tool_status_closed_set_verbatim() -> None:
    """03 §6: active|disabled."""
    assert {s.value for s in ToolStatus} == {"active", "disabled"}


def test_approval_requirement_closed_set_verbatim() -> None:
    """14 §4 example values: none|before_action|always."""
    assert {a.value for a in ApprovalRequirement} == {"none", "before_action", "always"}


def test_provider_agent_tool_class_closed_set_verbatim() -> None:
    """14 §11: the four classifications, verbatim."""
    assert {c.value for c in ProviderAgentToolClass} == {
        "provider_internal_tool",
        "platform_tool",
        "hybrid_tool",
        "unknown_tool",
    }


def test_unclassified_provider_agent_tool_defaults_to_unknown() -> None:
    """14 §11: unknown provider-side tools default to DENY/disabled — the
    default classification must therefore be the one that maps to DENY."""
    assert DEFAULT_PROVIDER_AGENT_TOOL_CLASS is ProviderAgentToolClass.UNKNOWN_TOOL


def test_firewall_check_order_is_14_s7_verbatim() -> None:
    """14 §7 list, in the spec's order (data for the later Phase 14 machinery)."""
    assert FIREWALL_CHECK_ORDER == (
        "identity",
        "tenant",
        "permission",
        "entitlement",
        "resource_ownership",
        "scope",
        "approval_policy",
        "tool_sandbox_policy",
        "rate_limit",
        "audit",
    )


# --- Manifest (14 §4) --------------------------------------------------------------


def _manifest(**overrides: object) -> ToolManifest:
    base: dict[str, object] = {
        "id": "github",
        "name": "GitHub",
        "version": "1.0.0",
        "location": "server",
        "status": "active",
        "permissions": [
            "github.repo.read",
            "github.commit.create",
            "github.pr.merge",
        ],
        "credentials": {"supported_owners": ["platform", "user"]},
        "approval_policy": {
            "github.repo.read": "none",
            "github.commit.create": "before_action",
            "github.pr.merge": "always",
        },
        "sandbox_policy": {"network": "restricted", "filesystem": "none"},
    }
    base.update(overrides)
    return ToolManifest.model_validate(base)


def test_manifest_accepts_the_14_s4_github_example_shape() -> None:
    manifest = _manifest()
    assert manifest.id == "github"
    assert manifest.location is ToolLocation.SERVER
    assert manifest.credentials.supported_owners[0].value == "platform"
    assert manifest.approval_for("github.pr.merge") is ApprovalRequirement.ALWAYS


def test_manifest_defaults_are_deny_by_default() -> None:
    """A minimal manifest grants nothing and is not active."""
    manifest = ToolManifest.model_validate(
        {"id": "t", "name": "T", "version": "1.0.0", "location": "client"}
    )
    assert manifest.status is ToolStatus.DISABLED
    assert manifest.permissions == []
    assert manifest.approval_policy == {}
    assert manifest.credentials.supported_owners == []
    assert manifest.rate_limits is None


def test_manifest_rejects_approval_entry_for_undeclared_permission() -> None:
    """An approval_policy key that is not a declared permission is a
    contract error (implicit-grant smuggling / typo)."""
    with pytest.raises(ValidationError, match="undeclared permissions"):
        _manifest(
            permissions=["github.repo.read"],
            approval_policy={"github.pr.merge": "none"},
        )


def test_declared_permission_without_approval_entry_needs_full_approval() -> None:
    """41 §1 rule 9 (unknown ⇒ DENY): an unlisted declared permission
    resolves to the MOST restrictive requirement, never a silent 'none'."""
    manifest = _manifest(
        permissions=["github.repo.read", "github.branch.create"],
        approval_policy={"github.repo.read": "none"},
    )
    assert DEFAULT_APPROVAL_REQUIREMENT is ApprovalRequirement.ALWAYS
    assert manifest.approval_for("github.branch.create") is ApprovalRequirement.ALWAYS


def test_approval_lookup_for_undeclared_permission_raises() -> None:
    """Asking about a permission the tool never declared is a caller bug —
    KeyError, never a default that could read as a grant."""
    manifest = _manifest()
    with pytest.raises(KeyError):
        manifest.approval_for("github.issue.write")


def test_manifest_rejects_unknown_fields() -> None:
    """ContractModel posture: extra=forbid."""
    with pytest.raises(ValidationError):
        ToolManifest.model_validate(
            {
                "id": "t",
                "name": "T",
                "version": "1.0.0",
                "location": "server",
                "grants": ["admin"],  # not a field — must not smuggle through
            }
        )


def test_manifest_rejects_invalid_location_and_status() -> None:
    with pytest.raises(ValidationError):
        _manifest(location="serverless")
    with pytest.raises(ValidationError):
        _manifest(status="enabled")


def test_manifest_is_frozen() -> None:
    manifest = _manifest()
    with pytest.raises(ValidationError):
        manifest.status = ToolStatus.DISABLED  # type: ignore[misc]


def test_credentials_spec_reuses_03_s4_owner_closed_set() -> None:
    """No duplicate owner enum: values are the 03 §4 platform/tenant/user set."""
    spec = ToolCredentialsSpec.model_validate(
        {"supported_owners": ["platform", "tenant", "user"]}
    )
    assert [o.value for o in spec.supported_owners] == ["platform", "tenant", "user"]
    with pytest.raises(ValidationError):
        ToolCredentialsSpec.model_validate({"supported_owners": ["provider"]})


# --- Entity (03 §6) ----------------------------------------------------------------


def _tool(**overrides: object) -> Tool:
    base: dict[str, object] = {
        "id": uuid4(),
        "name": "github",
        "version": "1.0.0",
        "location": "server",
        "permissions": ["github.repo.read"],
        "input_schema": {},
        "output_schema": {},
        "sandbox_policy": {"network": "restricted"},
        "approval_policy": {"github.repo.read": "none"},
        "status": "active",
    }
    base.update(overrides)
    return Tool.model_validate(base)


def test_tool_entity_fields_match_03_s6() -> None:
    """03 §6 Tool entity, field-for-field."""
    assert set(Tool.model_fields) == {
        "id",
        "name",
        "version",
        "location",
        "permissions",
        "input_schema",
        "output_schema",
        "sandbox_policy",
        "approval_policy",
        "status",
    }


def test_tool_entity_roundtrip() -> None:
    tool = _tool()
    assert tool.location is ToolLocation.SERVER
    assert tool.status is ToolStatus.ACTIVE
    assert Tool.model_validate(tool.model_dump()) == tool


def test_tool_entity_defaults_to_disabled_with_no_permissions() -> None:
    tool = Tool.model_validate(
        {"id": uuid4(), "name": "t", "version": "1.0.0", "location": "client"}
    )
    assert tool.status is ToolStatus.DISABLED
    assert tool.permissions == []


def test_tool_entity_rejects_unknown_fields_and_is_frozen() -> None:
    with pytest.raises(ValidationError):
        _tool(capability_grants=["all"])
    tool = _tool()
    with pytest.raises(ValidationError):
        tool.status = ToolStatus.DISABLED  # type: ignore[misc]


def test_contract_module_imports_no_implementation() -> None:
    """41 §4 rule: no Contract imports a specific Implementation."""
    import core.contracts.tools as tools_module

    source = open(tools_module.__file__, encoding="utf-8").read()  # noqa: SIM115
    for forbidden in ("import httpx", "import fastapi", "import sqlalchemy", "import redis"):
        assert forbidden not in source
    # Only contract-layer imports from within the project:
    for line in source.splitlines():
        if line.startswith("from core.") and "core.contracts" not in line:
            raise AssertionError(f"non-contract project import: {line}")
