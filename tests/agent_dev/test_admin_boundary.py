"""R169 A4 — INV-7 guard: the admin agent's registry and permission classes are not widened.

The development agent lives in ``apps/agent_dev`` as a separately composed
surface. These tests snapshot the admin agent's public tool names and class
sets so that any accidental widening fails loudly.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from apps.admin_agent.contracts import (
    AA2_REGISTRABLE_CLASSES,
    AA3_REGISTRABLE_CLASSES,
    NEVER_REGISTRABLE_CLASSES,
    ToolClass,
)
from apps.admin_agent.dispatcher import ToolRegistry as AdminToolRegistry
from apps.admin_agent.tools import AgentToolSurface
from apps.agent_dev.surface import (
    DEV_TOOL_NAMES,
    DevAgentSurface,
    build_dev_surface,
    dev_tenant_policy,
)
from core.audit.memory import InMemoryAuditLog
from core.security.firewall import CapabilityFirewall
from core.tools.source_reader import SourceReader
from core.usage.memory import InMemoryUsageAccounting
from tests.admin_agent.test_aa2_admin_agent import AgentWorld
from tests.admin_agent.test_source_tools import world_with_source

ADMIN_BASE_NAMES: tuple[str, ...] = (
    "draft_change",
    "list_changes",
    "list_executions",
    "list_models",
    "list_providers",
    "preview_change",
    "read_audit",
    "read_execution",
    "run_test_execution",
    "usage_summary",
    "validate_change",
)
ADMIN_SOURCE_NAMES: tuple[str, ...] = ("list_source_files", "read_source_file", "search_source")
ADMIN_CLASSES = {ToolClass.R0_READ, ToolClass.R1_EXECUTE_TEST, ToolClass.R2_CONFIG_CHANGE}
FORBIDDEN_FRAGMENTS = ("write", "git", "github", "publish", "commit", "push")


def _dev_surface(root: Path) -> DevAgentSurface:
    tenant = uuid4()
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(tenant, dev_tenant_policy(write=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(tenant, plan="test", task_units_limit=100)
    return build_dev_surface(
        root=root,
        tenant_id=tenant,
        firewall=firewall,
        audit=InMemoryAuditLog(),
        usage=usage,
    )


def test_admin_base_registry_names_snapshot() -> None:
    assert sorted(AgentWorld().registry.names()) == sorted(ADMIN_BASE_NAMES)


def test_admin_with_source_registry_names_snapshot(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    world = world_with_source(tmp_path)
    assert sorted(world.registry.names()) == sorted(ADMIN_BASE_NAMES + ADMIN_SOURCE_NAMES)


def test_admin_tool_classes_never_include_source_change(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    world = world_with_source(tmp_path)
    classes = {ToolClass(str(entry["class"])) for entry in world.registry.describe()}
    assert classes <= ADMIN_CLASSES
    assert classes.isdisjoint(NEVER_REGISTRABLE_CLASSES)


def test_admin_tool_names_carry_no_write_or_git_fragment(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    world = world_with_source(tmp_path)
    for name in world.registry.names():
        assert not any(fragment in name.lower() for fragment in FORBIDDEN_FRAGMENTS), name


def test_dev_tool_names_are_disjoint_from_admin_names() -> None:
    assert set(DEV_TOOL_NAMES).isdisjoint(ADMIN_BASE_NAMES + ADMIN_SOURCE_NAMES)


def test_admin_permission_classes_unchanged() -> None:
    assert AA2_REGISTRABLE_CLASSES == frozenset({ToolClass.R0_READ, ToolClass.R1_EXECUTE_TEST})
    assert AA3_REGISTRABLE_CLASSES == AA2_REGISTRABLE_CLASSES | {ToolClass.R2_CONFIG_CHANGE}
    assert NEVER_REGISTRABLE_CLASSES == frozenset(
        {ToolClass.R3_SOURCE_CHANGE, ToolClass.R4_FORBIDDEN}
    )
    assert len(ToolClass) == 5


def test_admin_surface_has_reader_only_not_writer() -> None:
    annotations = AgentToolSurface.__annotations__
    assert annotations["repo_reader"] in ("SourceReader | None", SourceReader | None)
    for field_name in annotations:
        assert not any(fragment in field_name.lower() for fragment in FORBIDDEN_FRAGMENTS), (
            field_name
        )


def test_admin_registry_is_closed() -> None:
    assert not hasattr(AdminToolRegistry, "register")
    assert AdminToolRegistry([]).names() == []


def test_building_dev_surface_leaves_admin_registry_unchanged(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    before = sorted(AgentWorld().registry.names())
    _dev_surface(tmp_path)
    after = sorted(AgentWorld().registry.names())
    assert before == after == sorted(ADMIN_BASE_NAMES)
