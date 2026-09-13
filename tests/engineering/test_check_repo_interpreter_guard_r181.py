"""F-R175-04 (closed R181): the gate fails closed when ``python3`` lacks the dev toolchain.

Measured in R175: ``check_repo.sh`` run outside the venv reported 86 pytest
collection errors and FAIL — a misleading verdict that looked like repository
breakage. The guard (step 1b) checks ``import pytest, mypy, ruff`` on the very
``python3`` the script uses and stops with the documented install path BEFORE
any slice runs. Inside the venv the guard is a no-op (the canonical gate result
is unchanged).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "engineering" / "verification" / "check_repo.sh"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_guard_sits_after_manifest_json_check_and_before_any_slice() -> None:
    text = _script()
    guard = text.index('python3 -c "import pytest, mypy, ruff"')
    assert text.index("green manifest is not valid JSON") < guard
    assert guard < text.index("# 4a. pytest")  # pytest slices come later
    # Fails closed: sets FAIL, prints the verdict line, exits non-zero.
    block = text[guard : text.index("\nfi\n", guard)]
    assert 'fail "python3 on PATH lacks the dev toolchain' in block
    assert 'note "RESULT: FAIL"' in block and "exit 1" in block
    assert "pip install -e '.[dev]'" in block


def test_guard_fails_closed_on_a_bare_interpreter(tmp_path: Path) -> None:
    """A shim `python3` without pytest → early FAIL with the install hint."""
    shim = tmp_path / "bin"
    shim.mkdir()
    fake = shim / "python3"
    # The shim imports json fine (manifest check passes) but has no dev tools.
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$*" == *pytest* ]]; then exit 1; fi\n'
        f'exec {os.environ.get("REAL_PY", "/usr/bin/python3")} "$@"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    env = {"PATH": f"{shim}:/usr/bin:/bin", "HOME": str(tmp_path), "REAL_PY": "/usr/bin/python3"}
    r = subprocess.run(
        ["bash", str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, env=env, timeout=120
    )
    assert r.returncode != 0
    assert "lacks the dev toolchain" in r.stdout
    assert "RESULT: FAIL" in r.stdout
    # Stopped BEFORE any pytest slice ran (no misleading collection errors).
    assert "slice" not in r.stdout.lower() and "collected" not in r.stdout
