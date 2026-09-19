"""Contract Freeze Baseline GUARD (R189, R189-DEC-01).

Distinct from the repository's *port conformance* suites (which check that an
adapter honours a Port's behaviour). THIS guard checks that the FROZEN
CONTRACT SET has not drifted from the committed, derived baseline:

- the baseline is re-DERIVED from the live tree by
  ``engineering/verification/contract_freeze_derive.py`` (introspection of the
  frozen modules + the app's OpenAPI route table — never a hand roster);
- any REMOVAL / RENAME / TYPE or REQUIREDNESS change of a frozen field, any
  enum-member change, any closed-set constant change, any served /v1 route
  removal or method removal ⇒ FAIL naming the exact path;
- any ADDITION not yet in the committed baseline ⇒ FAIL too: a frozen contract
  changes only through an explicitly declared round that re-derives the
  baseline (``--write --round=rNNN``) and records the change in
  60_DECISION_LOG.md. "Additive-only" is the compatibility rule for consumers,
  not a licence to mutate the baseline silently.

RED/GREEN proof of the guard itself lives in ``evidence/r189/``
(deliberate mutation → FAIL → revert → PASS).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
DERIVE = ROOT / "engineering" / "verification" / "contract_freeze_derive.py"
BASELINE = ROOT / "engineering" / "verification" / "contract_freeze_baseline.json"


def _load_derive() -> Any:
    spec = importlib.util.spec_from_file_location("contract_freeze_derive", DERIVE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["contract_freeze_derive"] = module
    spec.loader.exec_module(module)
    return module


def _diff(expected: Any, actual: Any, path: str, out: list[str]) -> None:
    """Human-readable, path-qualified differences (both directions)."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            sub = f"{path}.{key}" if path else str(key)
            if key not in actual:
                out.append(f"REMOVED  {sub}")
            elif key not in expected:
                out.append(f"ADDED    {sub} (not in committed baseline — declare a round and re-derive)")
            else:
                _diff(expected[key], actual[key], sub, out)
    elif isinstance(expected, list) and isinstance(actual, list):
        if expected != actual:
            missing = [e for e in expected if e not in actual]
            extra = [a for a in actual if a not in expected]
            for item in missing:
                out.append(f"REMOVED  {path}[] {json.dumps(item, default=str)[:160]}")
            for item in extra:
                out.append(f"ADDED    {path}[] {json.dumps(item, default=str)[:160]}")
            if not missing and not extra:
                out.append(f"REORDERED {path}")
    elif expected != actual:
        out.append(f"CHANGED  {path}: {expected!r} -> {actual!r}")


@pytest.fixture(scope="module")
def derived() -> dict[str, Any]:
    return _load_derive().derive()


@pytest.fixture(scope="module")
def committed() -> dict[str, Any]:
    assert BASELINE.exists(), "contract_freeze_baseline.json is missing — derive it in a declared round"
    return json.loads(BASELINE.read_text())


def test_baseline_is_derived_not_hand_maintained(committed: dict[str, Any]) -> None:
    assert committed["derived_by"] == "engineering/verification/contract_freeze_derive.py"
    assert committed["schema"] == "qevion.contract_freeze_baseline/1"
    assert committed["frozen_at"]["round"], "the freezing round must be recorded"
    # No roster of provider/model/capability NAMES lives in the baseline: the
    # served route table and contract shapes are the only served-truth content.
    text = json.dumps(committed)
    for roster_word in ("groq", "genspark", "openai", "anthropic", "gpt-", "llama"):
        assert roster_word not in text.lower(), f"provider/model roster leaked: {roster_word}"


def test_frozen_contract_set_matches_committed_baseline(
    derived: dict[str, Any], committed: dict[str, Any]
) -> None:
    module = _load_derive()
    expected = module.strip_volatile(committed)
    problems: list[str] = []
    _diff(expected, derived, "", problems)
    assert not problems, "CONTRACT FREEZE DRIFT:\n  " + "\n  ".join(problems)


def test_every_frozen_module_is_importable_and_non_empty(derived: dict[str, Any]) -> None:
    for name, module in derived["modules"].items():
        assert module["contracts"], f"{name} froze nothing — remove it from FROZEN_MODULES or fix"


def test_served_surface_contains_the_execute_read_paths(derived: dict[str, Any]) -> None:
    paths = {row["path"]: row["methods"] for row in derived["served_routes_v1"]}
    assert "POST" in paths["/v1/execute"]
    assert "GET" in paths["/v1/executions/{execution_id}"]
    assert "GET" in paths["/v1/models"]
    assert "GET" in paths["/v1/usage"]


def test_resource_signal_vocabulary_is_closed(derived: dict[str, Any]) -> None:
    snapshot = derived["resource_signal_snapshot"]
    assert snapshot["keys"] == sorted(
        ["provider_id", "model_id", "state", "reason", "cooldown_until", "rpm_used", "rpm_limit", "last_category"]
    )
    assert set(snapshot["states"]) == {"available", "unavailable", "cooldown", "limited"}


def test_learning_gates_carry_no_feedback_input(derived: dict[str, Any]) -> None:
    gates = derived["modules"]["core.learning.gates"]["contracts"]
    for name in ("EligibilitySignals", "PromotionSignals"):
        fields = gates[name]["fields"]
        assert not any("feedback" in f or "rating" in f for f in fields), name
