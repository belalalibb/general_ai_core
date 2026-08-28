"""Permission contract tests (FINAL Phase 3: 41 §6 ``permissions`` entity).

Verifies core/contracts/permission.py against its recorded authorities:
20 §4 identifier shape, 14 §8 catalog + approval rule, deny-by-default
posture (41 §1 rule 9), and the 41 §4 contracts-first rule.
"""

from __future__ import annotations

import ast
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.base import ContractModel
from core.contracts.permission import Permission
from core.contracts.tools import ApprovalRequirement

MODULE_PATH = Path("core/contracts/permission.py")

# 14 §8 — the GitHub permission catalog, verbatim.
GITHUB_CATALOG = [
    "github.repo.read",
    "github.issue.read",
    "github.issue.write",
    "github.branch.create",
    "github.commit.create",
    "github.pr.create",
    "github.pr.review",
    "github.pr.merge",
]


class TestDenyByDefault:
    def test_default_approval_is_always(self) -> None:
        # 41 §1 rule 9 + 14 §8 "Default write operations require approval":
        # an unconfigured permission requires approval EVERY time.
        permission = Permission(id=uuid4(), key="github.pr.merge")
        assert permission.approval is ApprovalRequirement.ALWAYS

    def test_relaxing_approval_must_be_explicit(self) -> None:
        permission = Permission(
            id=uuid4(), key="github.repo.read", approval=ApprovalRequirement.NONE
        )
        assert permission.approval is ApprovalRequirement.NONE


class TestSpecCatalogShape:
    @pytest.mark.parametrize("key", GITHUB_CATALOG)
    def test_14_s8_github_catalog_expressible(self, key: str) -> None:
        assert Permission(id=uuid4(), key=key).key == key

    def test_approval_values_are_the_closed_tools_set(self) -> None:
        # Reuse, not duplication: the same 14 §4 closed set the tool
        # manifest uses — no second approval enum exists.
        assert {m.value for m in ApprovalRequirement} == {"none", "before_action", "always"}


class TestValidationPosture:
    def test_frozen_and_extra_forbid(self) -> None:
        permission = Permission(id=uuid4(), key="github.repo.read")
        assert isinstance(permission, ContractModel)
        with pytest.raises(ValidationError):
            permission.key = "changed"  # type: ignore[misc]
        with pytest.raises(ValidationError):
            Permission(id=uuid4(), key="x", description="invented")  # type: ignore[call-arg]

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Permission(id=uuid4(), key="")

    def test_unknown_approval_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Permission(id=uuid4(), key="x", approval="auto_allow")  # type: ignore[arg-type]

    def test_permission_is_platform_catalog_not_tenant_scoped(self) -> None:
        # Recorded derivation: grants per tenant are firewall policy DATA,
        # not catalog rows — the catalog itself carries no tenant_id.
        assert "tenant_id" not in Permission.model_fields

    def test_minimal_field_set_no_invented_fields(self) -> None:
        # 41 §31 scope control: the specs define identifier + approval
        # posture only — the entity must not grow silent extras.
        assert set(Permission.model_fields) == {"id", "key", "approval"}


class TestContractsFirstRule:
    """41 §4: no Contract imports a specific Implementation."""

    def test_no_implementation_imports(self) -> None:
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
        allowed = {"__future__", "uuid", "core"}
        assert imported <= allowed, f"unexpected imports: {imported - allowed}"
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("core"):
                assert node.module.startswith("core.contracts."), node.module
