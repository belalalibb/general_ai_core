"""Guards for the single verifier and its green manifest (R168 §6.1/§6.2/§6.4/§2).

The shell sections of ``engineering/verification/check_repo.sh`` are executed for
real inside a temporary git skeleton so that the gate's FAIL paths are proven,
not assumed (INV-5).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "engineering" / "verification" / "check_repo.sh"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"
BASELINE = ROOT / "engineering" / "verification" / "green_manifest.baseline.json"

PRELUDE = (
    "set -u\n"
    "FAIL=0\n"
    "note() { printf '%s\\n' \"$*\"; }\n"
    "fail() { FAIL=1; printf 'FAIL: %s\\n' \"$*\"; }\n"
    "pass() { printf 'PASS: %s\\n' \"$*\"; }\n"
    'MANIFEST="engineering/verification/green_manifest.json"\n'
    "mf() { python3 -c \"import json,sys;m=json.load(open('$MANIFEST'));"
    'exec(sys.argv[1])" "$1"; }\n'
)
EXIT_LINE = '\nif [ "$FAIL" -eq 0 ]; then exit 0; else exit 1; fi\n'


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    text = _script()
    i = text.index(start)
    j = text.index(end, i)
    return text[i:j]


def _secret_section() -> str:
    return _section("# 5. Secret scan", "# 6. Production change budget")


def _budget_section() -> str:
    return _section("# 6. Production change budget", "# 7. NOT EVALUATED")


def _ne_section() -> str:
    return _section("# 7. NOT EVALUATED", 'if [ "$FAIL" -eq 0 ]; then\n  note "RESULT')


def _skeleton(tmp_path: Path, manifest: dict | None = None) -> Path:
    repo = tmp_path / "repo"
    (repo / "engineering" / "verification").mkdir(parents=True)
    data = manifest if manifest is not None else _manifest()
    (repo / "engineering" / "verification" / "green_manifest.json").write_text(
        json.dumps(data, indent=1), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    return repo


def _run_section(repo: Path, body: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
    )
    return subprocess.run(
        ["bash", "-c", PRELUDE + body + EXIT_LINE],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )


# --- static structure -------------------------------------------------------


def test_script_reads_manifest_and_never_silences() -> None:
    text = _script()
    assert 'MANIFEST="engineering/verification/green_manifest.json"' in text
    assert "|| true" not in text
    assert "set -u" in text
    for marker in (
        "# 4a. pytest",
        "# 5. Secret scan",
        "# 6. Production change budget",
        "# 7. NOT EVALUATED",
    ):
        assert marker in text, marker


def test_manifest_names_check_repo_as_authority() -> None:
    m = _manifest()
    assert "check_repo.sh" in m["authority"]
    assert m["pytest"]["gate"]["failed"] == 0
    assert m["pytest"]["gate"]["errors"] == 0


def test_slices_partition_tests_directory() -> None:
    """AH guard: every tests/<pkg> directory belongs to exactly one slice."""
    m = _manifest()
    declared: list[str] = []
    for s in m["pytest"]["slices"]:
        declared.extend(s["selection"].split())
    assert len(declared) == len(set(declared)), "a path appears in two slices"
    on_disk = sorted(
        f"tests/{p.name}"
        for p in (ROOT / "tests").iterdir()
        if p.is_dir() and not p.name.startswith(("__", "."))
    )
    missing = sorted(set(on_disk) - set(declared))
    assert not missing, f"tests directories not covered by any slice: {missing}"


def test_slice_paths_exist() -> None:
    for s in _manifest()["pytest"]["slices"]:
        for p in s["selection"].split():
            assert (ROOT / p).is_dir(), p


def test_gate_floor_and_ceiling_vs_baseline() -> None:
    m, b = _manifest(), _baseline()
    assert m["pytest"]["gate"]["min_passed"] >= b["pytest"]["passed"]
    assert m["pytest"]["gate"]["max_skipped"] <= b["pytest"]["skipped"]
    assert m["ui_static_check"]["v1_count_ceiling_N0"] <= b["ui"]["v1_count_N0"]
    assert m["ui_static_check"]["exception_count_ceiling"] == 0
    assert m["secret_scan"]["exception_count_ceiling"] <= 5
    assert m["not_evaluated_count_ceiling"] <= m["baseline"]["not_evaluated_count"]


def test_not_evaluated_reasons_are_closed_set() -> None:
    m = _manifest()
    closed = set(m["not_evaluated_reason_closed_set"])
    assert closed == {"missing dependency", "credential unavailable", "environment unavailable"}
    for it in m["not_evaluated"]:
        assert it["reason"] in closed, it
    assert len(m["not_evaluated"]) <= m["not_evaluated_count_ceiling"]


def test_change_budget_consistent() -> None:
    cb = _manifest()["change_budget"]
    for r in ("round_a", "round_b"):
        rd = cb[r]
        assert rd["ceiling"] == 5
        assert rd["changes_used"] <= rd["ceiling"]
        assert rd["changes_used"] == len(rd["log"])
        for e in rd["log"]:
            assert {"item", "file", "loc"} <= set(e)


def test_secret_exceptions_are_real_hits_and_reasons_do_not_self_match() -> None:
    m = _manifest()
    pattern = re.compile(m["secret_scan"]["patterns"])
    for e in m["secret_scan"]["exceptions"]:
        lines = (ROOT / e["file"]).read_text(encoding="utf-8").splitlines()
        assert pattern.search(lines[e["line"] - 1]), f"{e['file']}:{e['line']} is not a hit"
        assert not pattern.search(e["reason"]), "exception reason must not match the pattern"
    assert not pattern.search(MANIFEST.read_text(encoding="utf-8"))


# --- executed shell sections -----------------------------------------------


def test_secret_scan_fails_on_planted_secret(tmp_path: Path) -> None:
    repo = _skeleton(tmp_path)
    (repo / "apps").mkdir()
    token = "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    (repo / "apps" / "leak.py").write_text(f'TOKEN = "{token}"\n', encoding="utf-8")
    r = _run_section(repo, _secret_section())
    assert r.returncode == 1, r.stdout + r.stderr
    assert "possible secret detected outside the exception list" in r.stdout
    assert "apps/leak.py:1" in r.stdout


def test_secret_scan_passes_on_clean_tree(tmp_path: Path) -> None:
    repo = _skeleton(tmp_path)
    r = _run_section(repo, _secret_section())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "secret scan clean (declared exceptions: 5/5)" in r.stdout
    assert "no .env tracked" in r.stdout


def test_secret_scan_fails_on_tracked_env(tmp_path: Path) -> None:
    repo = _skeleton(tmp_path)
    (repo / ".env").write_text("X=1\n", encoding="utf-8")
    (repo / ".env.example").write_text("X=\n", encoding="utf-8")
    subprocess.run(["git", "add", "-f", ".env", ".env.example"], cwd=repo, check=True)
    r = _run_section(repo, _secret_section())
    assert r.returncode == 1
    assert ".env file is git-tracked: .env" in r.stdout
    assert ".env.example" not in r.stdout.split("git-tracked:")[1].splitlines()[0]


def test_secret_scan_fails_when_exceptions_exceed_ceiling(tmp_path: Path) -> None:
    m = _manifest()
    m["secret_scan"]["exceptions"].append({"file": "x.py", "line": 1, "reason": "extra"})
    repo = _skeleton(tmp_path, m)
    r = _run_section(repo, _secret_section())
    assert r.returncode == 1
    assert "exception list (6) exceeds ceiling (5)" in r.stdout


def test_not_evaluated_section_prints_lines_and_summary(tmp_path: Path) -> None:
    repo = _skeleton(tmp_path)
    r = _run_section(repo, _ne_section())
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("NOT EVALUATED: ") == 2
    assert "SUMMARY: not_evaluated=2 (counted separately; never green, never FAIL)" in r.stdout
    assert "PASS:" not in r.stdout


def test_not_evaluated_fails_on_reason_outside_closed_set(tmp_path: Path) -> None:
    m = _manifest()
    m["not_evaluated"][0]["reason"] = "deferred"
    repo = _skeleton(tmp_path, m)
    r = _run_section(repo, _ne_section())
    assert r.returncode == 1
    assert "not_evaluated malformed" in r.stdout


def test_budget_section_fails_when_over_ceiling(tmp_path: Path) -> None:
    m = _manifest()
    m["change_budget"]["round_a"]["changes_used"] = 6
    repo = _skeleton(tmp_path, m)
    r = _run_section(repo, _budget_section())
    assert r.returncode == 1
    assert "change budget exceeded" in r.stdout


def test_budget_section_passes_on_current_manifest(tmp_path: Path) -> None:
    repo = _skeleton(tmp_path)
    r = _run_section(repo, _budget_section())
    assert r.returncode == 0, r.stdout + r.stderr
    assert "change budget within ceilings" in r.stdout


@pytest.mark.parametrize(
    "rel",
    ["evidence/r168_state_ledger.md", "evidence/defect_ledger.md"],
)
def test_r168_ledgers_present(rel: str) -> None:
    assert (ROOT / rel).is_file()
