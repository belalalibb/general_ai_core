"""Parity tests — keep code, docs, and the template from drifting.

Authority rule (stated in both files): gateway/contracts.py is the code
source of truth; docs/CONTRACT.md is the human-readable mirror. These
tests fail when they drift.
"""

from __future__ import annotations

import re
from pathlib import Path

from gateway.contracts import (
    EXCLUDED_OPERATIONS,
    ErrorCategory,
    GatewayOperation,
)

ROOT = Path(__file__).resolve().parent.parent
CONTRACT_MD = (ROOT / "docs" / "CONTRACT.md").read_text(encoding="utf-8")
TEMPLATE_ADAPTER = (ROOT / "providers" / "_template" / "adapter.py").read_text(encoding="utf-8")


def test_contract_md_lists_all_12_categories_verbatim() -> None:
    for category in ErrorCategory:
        assert f"`{category.value}`" in CONTRACT_MD, f"CONTRACT.md missing {category.value}"


def test_contract_md_lists_all_8_operations() -> None:
    for operation in GatewayOperation:
        assert f"`{operation.value}`" in CONTRACT_MD, f"CONTRACT.md missing {operation.value}"


def test_contract_md_names_the_exclusions() -> None:
    for excluded in EXCLUDED_OPERATIONS:
        assert excluded in CONTRACT_MD


def test_contract_md_declares_code_as_source_of_truth() -> None:
    assert "gateway/contracts.py" in CONTRACT_MD
    assert "source of truth" in CONTRACT_MD.lower()


def test_contract_md_has_required_sections() -> None:
    required = (
        "INTERNAL IMPLEMENTATION FREEDOM",
        "ONE REQUEST → ONE CANONICAL RESPONSE",
        "X-Route-Token",
        "X-Gateway-Secret",
    )
    for section in required:
        assert section in CONTRACT_MD, f"CONTRACT.md missing section/term: {section}"


def test_template_documents_every_v1_operation() -> None:
    """D2-bis guarantee: the template has a documented stub per operation."""

    for operation in GatewayOperation:
        pattern = rf"async def {operation.value}\("
        assert re.search(pattern, TEMPLATE_ADAPTER), f"_template missing stub {operation.value}"


_APP_IMPORT = re.compile(r"^\s*(from app[ .]|import app\b)", re.MULTILINE)
"""Matches real import STATEMENTS of `app` (docstrings that merely mention
the forbidden pattern as a warning are not import statements)."""


def _actual_app_imports(source: str) -> list[str]:
    import ast

    tree = ast.parse(source)
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits.extend(a.name for a in node.names if a.name == "app" or a.name.startswith("app."))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "app" or node.module.startswith("app."):
                hits.append(node.module)
    return hits


def test_template_never_imports_app() -> None:
    """Dependency direction fix: providers import gateway.contracts, never app."""

    assert _actual_app_imports(TEMPLATE_ADAPTER) == []
    assert "from gateway.contracts import" in TEMPLATE_ADAPTER


def test_example_never_imports_app() -> None:
    for name in ("adapter.py", "_engine.py", "_wire.py", "definition.py"):
        text = (ROOT / "providers" / "_example" / name).read_text(encoding="utf-8")
        assert _actual_app_imports(text) == [], f"{name} imports app"
