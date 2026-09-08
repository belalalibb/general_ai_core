"""R177-FIX-01 — change-budget enforcement must cover EVERY manifest round.

F-R177-01: ``engineering/verification/check_repo.sh`` step 6 iterated a hardcoded
five-round tuple, so a new ``round_*`` block in ``green_manifest.json`` (R176/R177)
was silently unguarded. These tests execute the *real* python snippet embedded in
the gate script against fixture manifests, so the gate logic itself is pinned.
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CHECK_REPO = ROOT / "engineering" / "verification" / "check_repo.sh"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"

_BUDGET_START = "BUDGET=$(mf '"


def _budget_snippet() -> str:
    text = CHECK_REPO.read_text(encoding="utf-8")
    start = text.index(_BUDGET_START) + len(_BUDGET_START)
    end = text.index("')", start)
    return text[start:end]


def _run_budget(manifest: dict[str, Any]) -> str:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(_budget_snippet(), {"m": manifest})  # noqa: S102 - gate code under test
    return buf.getvalue().strip()


def _base_manifest() -> dict[str, Any]:
    return {
        "change_budget": {
            "counts_production_code_under": ["core/", "apps/", "infrastructure/"],
            "round_a": {
                "ceiling": 1,
                "changes_used": 1,
                "items": ["X-1 something"],
                "log": [{"item": "X-1", "file": "core/x.py"}],
            },
        }
    }


def test_unlisted_over_ceiling_round_fails_budget_step() -> None:
    """A round the tuple never named (round_zz) is over ceiling -> the step MUST say BAD."""
    m = _base_manifest()
    m["change_budget"]["round_zz"] = {
        "ceiling": 1,
        "changes_used": 2,
        "items": ["Z-1 a", "Z-2 b"],
        "log": [
            {"item": "Z-1", "file": "core/a.py"},
            {"item": "Z-2", "file": "core/b.py"},
        ],
    }
    out = _run_budget(m)
    assert out.startswith("BAD "), out
    assert "round_zz over ceiling" in out
    assert "round_zz=2/1" in out


def test_unlisted_round_log_count_mismatch_fails() -> None:
    m = _base_manifest()
    m["change_budget"]["round_r177"] = {
        "ceiling": 5,
        "changes_used": 0,
        "items": ["R177-FIX-02 x"],
        "log": [{"item": "R177-FIX-02", "file": "apps/api/x.py"}],
    }
    out = _run_budget(m)
    assert out.startswith("BAD "), out
    assert "round_r177 changes_used != len(log)" in out


def test_unlisted_round_outside_roots_and_unscheduled_item_fail() -> None:
    m = _base_manifest()
    m["change_budget"]["round_r177"] = {
        "ceiling": 5,
        "changes_used": 1,
        "items": ["R177-FIX-02 x"],
        "log": [{"item": "R177-FIX-99", "file": "docs/notes.md"}],
    }
    out = _run_budget(m)
    assert out.startswith("BAD "), out
    assert "round_r177 log file outside roots: docs/notes.md" in out
    assert "round_r177 item not scheduled: R177-FIX-99" in out


def test_non_round_keys_are_not_iterated() -> None:
    """Only ``round_*`` keys are budget rounds; other keys must not break the step."""
    m = _base_manifest()
    m["change_budget"]["frozen_note"] = "not a round"
    out = _run_budget(m)
    assert out.startswith("OK "), out
    assert "round_a=1/1" in out


def test_real_manifest_declares_round_r177_and_is_within_budget() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cb = m["change_budget"]
    assert "round_r177" in cb, "R177 Phase B production changes need a declared ceiling"
    rd = cb["round_r177"]
    assert rd["ceiling"] == 12
    assert rd["changes_used"] == len(rd["log"])
    assert rd["changes_used"] <= rd["ceiling"]
    assert rd["frozen_trees_zero_diff"] == ["ui/", "apps/admin_agent/", "core/tools/gate.py"]
    out = _run_budget(copy.deepcopy(m))
    assert out.startswith("OK "), out
    assert "round_r177=" in out


def test_real_manifest_every_round_key_appears_in_output() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out = _run_budget(copy.deepcopy(m))
    for key in m["change_budget"]:
        if key.startswith("round_"):
            assert f"{key}=" in out, f"{key} not enforced: {out}"
