"""R183 / F-R182-01 — the ``infrastructure/db/tables.py`` MODULE docstring must
agree with migration 0022 (R181 Q6, F-R179-06).

Finding (evidence/r182_findings_ledger.md F-R182-01): the module docstring's
``usage_ledger`` paragraph still described ``execution_id`` as
``UNIQUE + FK (RESTRICT: accounting records must never dangle)`` after 0022
dropped ``fk_usage_ledger_execution_id_executions``. The column-level comment
and the schema-parity pin
(tests/db/test_schema_contract_parity.py::test_usage_ledger_one_entry_per_execution_and_honest_defaults)
were already correct; only the prose was stale. Written RED before the
docstring edit (first act of R183); the metadata assertions are re-stated
here so the prose and the schema are pinned together.
"""

from __future__ import annotations

import re
from pathlib import Path

import infrastructure.db.tables as tables

ROOT = Path(__file__).resolve().parents[2]
TABLES_PY = ROOT / "infrastructure" / "db" / "tables.py"


def _usage_ledger_paragraph() -> str:
    doc = tables.__doc__ or ""
    m = re.search(r"- ``usage_ledger``.*?(?=\n- ``|\Z)", doc, re.DOTALL)
    assert m, "module docstring has no ``usage_ledger`` paragraph"
    return m.group(0)


def test_module_docstring_no_longer_claims_execution_id_is_a_foreign_key() -> None:
    para = _usage_ledger_paragraph()
    flat = " ".join(para.split())
    assert "UNIQUE + FK" not in flat, "F-R182-01: docstring still claims UNIQUE + FK"
    assert "accounting records must never dangle" not in flat, (
        "F-R182-01: the RESTRICT rationale belongs to the dropped FK"
    )


def test_module_docstring_states_the_0022_keying_posture() -> None:
    flat = " ".join(_usage_ledger_paragraph().split())
    # The prose must say what the schema does: NOT NULL + UNIQUE, no FK, and why.
    assert "NOT NULL" in flat and "UNIQUE" in flat
    assert re.search(r"\bNOT a foreign key\b|\bno foreign key\b|\bnot a FK\b", flat, re.IGNORECASE)
    assert "0022" in flat, "must cite the migration that dropped the FK"
    assert "F-R179-06" in flat or "R181" in flat, "must cite the deciding record"


def test_docstring_and_metadata_agree_on_usage_ledger_execution_id() -> None:
    column = tables.usage_ledger.columns["execution_id"]
    assert column.unique
    assert not column.nullable
    assert list(column.foreign_keys) == []
    # The stale wording must not survive anywhere in the file header either
    # (the module docstring is the first statement of the file).
    header = TABLES_PY.read_text(encoding="utf-8").split('"""', 2)[1]
    assert "UNIQUE + FK" not in header
