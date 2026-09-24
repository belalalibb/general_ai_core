"""R198-C (operator D1/D6) — the V1 acceptance register, read as TEXT.

NO SILENT LOSS: every deferred block of the R189 freeze record §6, every audit
decision (AD-1..AD-7, D-03, N-5, N-9), the R191/R192 open proposals, the manifest
``not_evaluated`` item and the UI-unconsumed routes must each appear as a register
row with a status from the closed set. The register may not claim "Production Ready"
while the D-03 row is OPERATOR-OWNED-OPEN (operator D1).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTER = ROOT / "docs" / "ai_orchestration_pack" / "V1_ACCEPTANCE_REGISTER.md"
FREEZE_R189 = ROOT / "evidence" / "r189" / "CONTRACT_FREEZE_RECORD.md"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"

STATUSES = {
    "ACCEPTED-AS-MEASURED",
    "DEFERRED-BY-RULING",
    "OPERATOR-OWNED-OPEN",
    "NOT-EVALUATED",
    "DECLARED-UNCONSUMED",
}
DECISION_IDS = ("AD-1", "AD-2", "AD-3", "AD-4", "AD-5", "AD-6", "AD-7", "D-03", "N-5", "N-9")
OPEN_PROPOSALS = ("P-R191-01", "P-R192-03")
UNCONSUMED_ROUTES = (
    "/v1/admin/evaluations/{",
    "/v1/webhooks/{",
)
# COMPLETION-V2-DEC-01 (C-17, operator D-5): GET /v1/admin/learning/dashboard left this tuple —
# it is MEASURED when the lifecycle is composed and consumed by the admin console Learning
# surface (1:1 swap for /learning/learned; 73 literals held). Pinned ACCEPTED-AS-MEASURED below.
CONSUMED_ROUTES_COMPLETION_V2 = ("/v1/admin/learning/dashboard",)
# R202-DEC-02 (operator ruling (a), step 7): GET /v1/templates/{ref} left this tuple and is
# pinned ACCEPTED-AS-MEASURED — R202-A only (Workbench detail panel; evidence/r202/).
# Lineage: DECLARED-UNCONSUMED since R197 D4 / R198 (this pin flipped 1:1, count unchanged).
CONSUMED_ROUTES_R202 = ("/v1/templates/{",)


def _register() -> str:
    assert REGISTER.is_file(), f"acceptance register absent: {REGISTER.relative_to(ROOT)}"
    return REGISTER.read_text(encoding="utf-8")


def _rows() -> list[list[str]]:
    """Rows of the status-bearing sections A–C (section D is measured facts, no status)."""
    rows = []
    text = _register()
    cut = text.find("## D.")
    body = text if cut == -1 else text[:cut]
    for line in body.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            rows.append(cells)
    return rows


def _row_for(token: str) -> list[str]:
    for r in _rows():
        if r and token in r[0]:
            return r
    raise AssertionError(f"register has no row for {token!r}")


def _status_of(row: list[str]) -> str:
    for c in row:
        if c in STATUSES:
            return c
    raise AssertionError(f"row {row[0]!r} carries no closed-set status: {row}")


def test_register_exists_with_status_column_closed_set() -> None:
    rows = [r for r in _rows() if r and r[0] not in ("id", "ID", "Item", "item", "route", "area")]
    assert len(rows) >= 20
    for r in rows:
        _status_of(r)


def test_every_r189_deferred_block_is_registered() -> None:
    ids = re.findall(r"^### (6\.\d+) ", FREEZE_R189.read_text(encoding="utf-8"), flags=re.M)
    assert len(ids) == 10, ids
    for i in ids:
        _status_of(_row_for(f"R189 §{i}"))


def test_every_audit_decision_is_registered() -> None:
    for d in DECISION_IDS:
        _status_of(_row_for(d))


def test_open_proposals_registered_as_deferred() -> None:
    for p in OPEN_PROPOSALS:
        assert _status_of(_row_for(p)) == "DEFERRED-BY-RULING"


def test_not_evaluated_item_registered() -> None:
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))["not_evaluated"]
    for it in items:
        assert _status_of(_row_for(it["item"][:40])) == "NOT-EVALUATED"


def test_ui_unconsumed_routes_declared() -> None:
    for route in UNCONSUMED_ROUTES:
        assert _status_of(_row_for(route)) == "DECLARED-UNCONSUMED"
    for route in CONSUMED_ROUTES_R202:
        row = _row_for(route)
        assert _status_of(row) == "ACCEPTED-AS-MEASURED"
        text = " | ".join(row)
        assert "R202-A" in text and "R202-B" in text and "DEFERRED" in text, (
            "the R202 flip must name its scope (R202-A only) and the deferred R202-B"
        )
    for route in CONSUMED_ROUTES_COMPLETION_V2:
        row = _row_for(route)
        assert _status_of(row) == "ACCEPTED-AS-MEASURED"
        text = " | ".join(row)
        assert "COMPLETION-V2" in text and "deferred" in text.lower(), (
            "the dashboard flip must name its program and that unmeasured metrics stay deferred"
        )


def test_d03_and_n9_operator_owned_until_evidence() -> None:
    d03 = _status_of(_row_for("D-03"))
    n9 = _status_of(_row_for("N-9"))
    if d03 == "OPERATOR-OWNED-OPEN":
        assert n9 == "OPERATOR-OWNED-OPEN", "N-9 is bound to the D-03 purge procedure (operator D5)"
    else:
        # closed only with evidence paths on the row
        assert "evidence/r198/" in " ".join(_row_for("D-03"))


def test_production_ready_not_claimed_while_d03_open() -> None:
    text = _register()
    if _status_of(_row_for("D-03")) == "OPERATOR-OWNED-OPEN":
        for m in re.finditer(r"production[- ]ready", text, flags=re.I):
            window = text[max(0, m.start() - 120) : m.start() + 60].lower()
            assert "not" in window or "never" in window or "no " in window, (
                "register must not claim Production Ready while D-03 is OPERATOR-OWNED-OPEN"
            )
        assert "as measured" in text.lower()
