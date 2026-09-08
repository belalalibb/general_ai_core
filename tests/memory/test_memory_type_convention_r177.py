"""R177-FIX-05 — memory-type convention pin (13 §2 types over the existing MemoryItem).

There is deliberately NO ``MemoryType`` enum (R177-DEFER-01). The type of a memory is
``scope`` × ``source`` × ``user_id``; this test pins the *source vocabulary* runtime
writers may use and keeps ``docs/architecture/MEMORY_TYPES_MAPPING.md`` in lock-step
with the code. Extending the vocabulary = edit the doc table AND this frozenset in one
approved, test-pinned change.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from core.learning.lifecycle import GOLD_KNOWLEDGE_SOURCE

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture" / "MEMORY_TYPES_MAPPING.md"

#: Closed source vocabulary for ``MemoryItem.source`` written by runtime code.
MEMORY_SOURCE_VOCABULARY: frozenset[str] = frozenset(
    {"learning.gold", "preference", "episode", "repo.map"}
)


def _module_constants(tree: ast.Module) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        consts[t.id] = node.value.value
    return consts


def _resolve_source(kw: ast.keyword, consts: dict[str, str], imports: dict[str, str]) -> str:
    v = kw.value
    if isinstance(v, ast.Constant) and isinstance(v.value, str):
        return v.value
    if isinstance(v, ast.Name):
        if v.id in consts:
            return consts[v.id]
        if v.id in imports:
            return imports[v.id]
    if isinstance(v, ast.Attribute):
        return f"<attr:{ast.unparse(v)}>"
    return f"<dynamic:{ast.unparse(v)}>"


def _imported_constants(tree: ast.Module) -> dict[str, str]:
    """Resolve ``from core.x import CONST`` where CONST is a module-level str constant."""
    out: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            mod_path = ROOT / (node.module.replace(".", "/") + ".py")
            if not mod_path.exists():
                continue
            target = _module_constants(ast.parse(mod_path.read_text(encoding="utf-8")))
            for alias in node.names:
                if alias.name in target:
                    out[alias.asname or alias.name] = target[alias.name]
    return out


def runtime_memory_item_sources() -> dict[str, list[str]]:
    """Every ``MemoryItem(... source=...)`` construction under core/ and apps/ (no tests)."""
    found: dict[str, list[str]] = {}
    for base in ("core", "apps"):
        for path in sorted((ROOT / base).rglob("*.py")):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if "MemoryItem(" not in text:
                continue
            tree = ast.parse(text)
            consts = _module_constants(tree)
            imports = _imported_constants(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
                if name != "MemoryItem":
                    continue
                for kw in node.keywords:
                    if kw.arg == "source":
                        rel = path.relative_to(ROOT).as_posix()
                        found.setdefault(rel, []).append(_resolve_source(kw, consts, imports))
    return found


def _doc_vocabulary() -> set[str]:
    text = DOC.read_text(encoding="utf-8")
    section = text.split("## 1. Source vocabulary", 1)[1].split("## 2.", 1)[0]
    return set(re.findall(r"^\| `([a-z][a-z0-9_.]*)` \|", section, flags=re.M))


def test_gold_source_is_in_vocabulary() -> None:
    assert GOLD_KNOWLEDGE_SOURCE in MEMORY_SOURCE_VOCABULARY


def test_every_runtime_writer_uses_vocabulary_source() -> None:
    found = runtime_memory_item_sources()
    assert found, "expected at least the GOLD writer in core/learning/lifecycle.py"
    assert "core/learning/lifecycle.py" in found
    for rel, sources in found.items():
        for src in sources:
            assert src in MEMORY_SOURCE_VOCABULARY, f"{rel}: unknown MemoryItem.source {src!r}"


def test_mapping_doc_exists_and_matches_pinned_vocabulary() -> None:
    assert DOC.exists(), "docs/architecture/MEMORY_TYPES_MAPPING.md is the convention authority"
    assert _doc_vocabulary() == set(MEMORY_SOURCE_VOCABULARY)


def test_no_memory_type_enum_introduced() -> None:
    """R177-DEFER-01: a MemoryType enum is NOT part of the contract."""
    import core.contracts.memory as mem

    assert not hasattr(mem, "MemoryType")


@pytest.mark.parametrize("bad", ["unknown", "Learning.Gold", "memory:abc", ""])
def test_vocabulary_rejects_non_members(bad: str) -> None:
    assert bad not in MEMORY_SOURCE_VOCABULARY
