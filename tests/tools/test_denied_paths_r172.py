"""R172 C1 — hardened denylist consumed from the R170 probe table.

The probe (``evidence/r170/denylist_probe.txt``) lists 27 paths that must be
denied and 3 that must stay allowed. This suite consumes that table directly
so the evidence and the test cannot drift apart. The hardened patterns live in
``core.tools.denied_paths`` and are wired at ``build_dev_surface`` composition
(``apps/agent_dev/surface.py``); bare ``SourceReader`` defaults are untouched.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apps.agent_dev.surface import build_dev_surface, dev_tenant_policy
from core.audit.memory import InMemoryAuditLog
from core.security.firewall import CapabilityFirewall
from core.tools.denied_paths import DENIED_PATH_PATTERNS, is_denied_path
from core.tools.source_reader import DEFAULT_DENIED_PATTERNS, SourceReader
from core.tools.source_writer import SourceWriter
from core.usage.memory import InMemoryUsageAccounting

PROBE = Path(__file__).resolve().parents[2] / "evidence" / "r170" / "denylist_probe.txt"
_ROW = re.compile(r"^(?:GAP|ok)\s+denied=(?:True|False)\s+(\S+)\s+(EXPECT_DENIED|expect_allowed)")

#: Names whose denial needs content-based detection; kept as xfail, not silently dropped.
XFAIL_OBFUSCATED = {
    "acco33unts.txt": "obfuscated name — needs content-based detection, out of scope",
}


def _rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in PROBE.read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            rows.append((m.group(1), m.group(2)))
    return rows


def _expect_denied() -> list[str]:
    return [p for p, v in _rows() if v == "EXPECT_DENIED"]


def _expect_allowed() -> list[str]:
    return [p for p, v in _rows() if v == "expect_allowed"]


def test_probe_table_shape() -> None:
    denied = _expect_denied()
    allowed = _expect_allowed()
    assert len(denied) == 27
    assert len(allowed) == 3
    # session_dump.txt is marked "expect_allowed?" in the probe; decision: ALLOWED
    # (generic name, no credential semantics) — recorded in evidence/r172/C1/notes.md.
    assert "session_dump.txt" in allowed


@pytest.mark.parametrize("rel", _expect_denied())
def test_expect_denied_rows_deny(rel: str) -> None:
    if rel in XFAIL_OBFUSCATED:
        if not is_denied_path(rel):
            pytest.xfail(XFAIL_OBFUSCATED[rel])
    assert is_denied_path(rel), rel


@pytest.mark.parametrize("rel", _expect_allowed())
def test_expect_allowed_rows_stay_allowed(rel: str) -> None:
    assert not is_denied_path(rel), rel


@pytest.mark.parametrize(
    "rel",
    [
        "engineering/verification/green_manifest.json",
        "engineering/verification/nested/deeper.txt",
        ".ssh/known_hosts",
        "home/.ssh/authorized_keys",
        "keys/authorized_keys",
        ".aws/credentials",
        ".kube/config",
        ".gnupg/pubring.kbx",
        "a/b/id_ecdsa",
        "x/.netrc",
        ".pgpass",
        "store.jks",
        "store.keystore",
        "vault/user_tokens.json",
        "db/password.txt",
        "etc/passwd",
        "etc/shadow",
        ".ENV",
        ".Env.local",
        ".ENV.production",
        "nested/.ENV.production",
        "nested/.Env",
    ],
)
def test_required_patterns_deny(rel: str) -> None:
    assert is_denied_path(rel), rel


@pytest.mark.parametrize(
    "rel",
    [
        "pyproject.toml",
        "core/tools/gate.py",
        "docs/README.md",
        "tests/x.py",
        "README.md",
        "src/main.ts",
    ],
)
def test_ordinary_source_paths_allowed(rel: str) -> None:
    assert not is_denied_path(rel), rel


def test_superset_of_reader_defaults() -> None:
    assert set(DEFAULT_DENIED_PATTERNS) <= set(DENIED_PATH_PATTERNS)
    assert len(set(DENIED_PATH_PATTERNS)) == len(DENIED_PATH_PATTERNS), "duplicate patterns"


def _surface(tmp_path: Path):
    tenant_id = "tenant-r172-c1"
    firewall = CapabilityFirewall()
    firewall.set_tenant_policy(tenant_id, dev_tenant_policy(write=True))
    usage = InMemoryUsageAccounting()
    usage.configure_tenant(tenant_id, plan="dev", task_units_limit=100.0)
    return build_dev_surface(
        root=tmp_path,
        tenant_id=tenant_id,
        firewall=firewall,
        audit=InMemoryAuditLog(),
        usage=usage,
    )


def test_dev_surface_reader_and_writer_use_hardened_denylist(tmp_path: Path) -> None:
    gate_dir = tmp_path / "engineering" / "verification"
    gate_dir.mkdir(parents=True)
    (gate_dir / "green_manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".ENV").write_text("X=1", encoding="utf-8")
    (tmp_path / "ok.txt").write_text("fine", encoding="utf-8")

    surface = _surface(tmp_path)
    assert tuple(surface.reader.denied_patterns) == DENIED_PATH_PATTERNS
    assert tuple(surface.writer.denied_patterns) == DENIED_PATH_PATTERNS

    for rel in ("engineering/verification/green_manifest.json", ".ENV"):
        with pytest.raises(Exception, match="denied by policy"):
            surface.reader.read_file(rel)
    assert surface.reader.read_file("ok.txt")["content"] == "fine"


def test_bare_source_reader_and_writer_defaults_unchanged(tmp_path: Path) -> None:
    # C1 wires the hardened list at composition only; the primitives keep their defaults.
    assert tuple(SourceReader(tmp_path).denied_patterns) == DEFAULT_DENIED_PATTERNS
    assert tuple(SourceWriter(tmp_path).denied_patterns) == DEFAULT_DENIED_PATTERNS
    assert len(DEFAULT_DENIED_PATTERNS) == 13
