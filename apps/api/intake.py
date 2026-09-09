"""Structured knowledge intake adapter — CSV/JSON batches → RAW samples (R177-FIX-10).

Closes G-A07-3 ("no bulk/structured intake"). Design, recorded at the binding:

- OUTSIDE core/: parsing and expectation-checking are composition concerns;
  the trust boundary stays exactly where it was — every admitted row enters
  through the EXISTING ``LearningLifecycleService.capture_external`` and is
  therefore RAW / PENDING / PENDING like any other external item. Nothing here
  can raise a verification level, mark sanitization, or promote.
- DECLARED EXPECTATIONS (composition data, per call): required columns, the
  column whose value becomes ``knowledge_key``, and ``max_rows``. A batch that
  violates a BATCH-level expectation (unparseable, wrong shape, over limit) is
  QUARANTINED — no row is captured, the report says why. A ROW that violates a
  row-level expectation (missing/blank required column) is REFUSED with its
  1-based row number and a named reason; the other rows proceed.
- SCAN AT INTAKE: each captured sample gets the deterministic 22 §12 secret
  scan run and RECORDED immediately (the lifecycle's own ``sanitize``). The
  report exposes only ``clean`` + findings (path, label, fingerprint) — never
  cell content. A flagged sample is still RAW and still tracked; the EXISTING
  ``mark_sanitized(passed=True)`` refusal keeps it from ever passing review,
  so poisoning through bulk upload is bounded by the same gate as before.
- BOUNDS: content size is capped (``MAX_CONTENT_BYTES``) and rows by the
  caller's ``max_rows`` (itself capped by ``MAX_ROWS_CEILING``); formats are a
  closed set (``INTAKE_FORMATS``). Excel is deliberately absent (would add an
  optional dependency; the assessment listed it as optional — deferred).
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from core.contracts.base import BoundedStr, ContractModel, JsonObject
from core.learning.lifecycle import LearningLifecycleService

__all__ = [
    "INTAKE_FORMATS",
    "MAX_CONTENT_BYTES",
    "MAX_ROWS_CEILING",
    "AdmittedRow",
    "IntakeAdapter",
    "IntakeExpectations",
    "IntakeReport",
    "IntakeRequest",
    "RefusedRow",
    "parse_intake_rows",
]

#: Closed set of accepted encodings (assessment §11 FIX-10: "CSV/JSON (Excel optional)").
INTAKE_FORMATS: frozenset[str] = frozenset({"csv", "json"})
#: Upper bound on one batch body (composition data; 41 §49 bounded surfaces).
MAX_CONTENT_BYTES = 256 * 1024
#: Hard ceiling on ``max_rows`` a caller may declare.
MAX_ROWS_CEILING = 1000

IntakeFormat = Literal["csv", "json"]


class IntakeExpectations(ContractModel):
    """What the caller DECLARES the batch must satisfy (composition data)."""

    required_columns: tuple[BoundedStr, ...] = Field(min_length=1, max_length=64)
    key_column: BoundedStr
    max_rows: int = Field(default=100, ge=1, le=MAX_ROWS_CEILING)

    @model_validator(mode="after")
    def _key_is_required(self) -> IntakeExpectations:
        if self.key_column not in self.required_columns:
            msg = "key_column must be one of required_columns"
            raise ValueError(msg)
        return self


class IntakeRequest(ContractModel):
    """POST /v1/admin/learning/intake body."""

    format: IntakeFormat
    content: str = Field(max_length=MAX_CONTENT_BYTES)
    expectations: IntakeExpectations


@dataclass(frozen=True)
class AdmittedRow:
    row: int
    sample_id: str
    knowledge_key: str
    scan_clean: bool
    findings: tuple[JsonObject, ...]

    def as_json(self) -> JsonObject:
        return {
            "row": self.row,
            "sample_id": self.sample_id,
            "knowledge_key": self.knowledge_key,
            "scan_clean": self.scan_clean,
            "findings": list(self.findings),
        }


@dataclass(frozen=True)
class RefusedRow:
    row: int
    reason: str

    def as_json(self) -> JsonObject:
        return {"row": self.row, "reason": self.reason}


@dataclass(frozen=True)
class IntakeReport:
    """One batch's outcome — the 'sample report' the assessment asked for."""

    rows: int
    admitted: tuple[AdmittedRow, ...] = ()
    refused: tuple[RefusedRow, ...] = ()
    quarantined: bool = False
    quarantine_reason: str | None = None
    format: str = ""
    columns_seen: tuple[str, ...] = field(default=())

    @property
    def flagged(self) -> int:
        return sum(1 for a in self.admitted if not a.scan_clean)

    def as_json(self) -> JsonObject:
        return {
            "format": self.format,
            "rows": self.rows,
            "columns_seen": list(self.columns_seen),
            "admitted": [a.as_json() for a in self.admitted],
            "refused": [r.as_json() for r in self.refused],
            "flagged": self.flagged,
            "quarantined": self.quarantined,
            "quarantine_reason": self.quarantine_reason,
        }


def _flat_row(value: object, index: int) -> dict[str, str]:
    if not isinstance(value, dict):
        msg = f"row {index} is not an object"
        raise ValueError(msg)
    flat: dict[str, str] = {}
    for key, cell in value.items():
        if cell is None:
            flat[str(key)] = ""
        elif isinstance(cell, str | int | float | bool):
            flat[str(key)] = str(cell)
        else:
            msg = f"row {index} column {key!r} is not a flat scalar"
            raise ValueError(msg)
    return flat


def parse_intake_rows(fmt: str, content: str) -> tuple[dict[str, str], ...]:
    """Decode ``content`` as ``fmt`` into flat string rows.

    Raises ``ValueError`` with a named reason for anything outside the closed
    format set or the expected shape (JSON: array of flat objects; CSV: header
    row + records). Cells are strings — typing beyond "present and non-blank"
    is not claimed (nothing invented).
    """
    if fmt not in INTAKE_FORMATS:
        msg = f"unknown intake format {fmt!r}; accepted: {sorted(INTAKE_FORMATS)}"
        raise ValueError(msg)
    if fmt == "json":
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as exc:
            msg = f"content is not valid JSON: {exc.msg}"
            raise ValueError(msg) from exc
        if not isinstance(decoded, list):
            msg = "JSON content must be an array of row objects"
            raise ValueError(msg)
        return tuple(_flat_row(item, index + 1) for index, item in enumerate(decoded))
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        msg = "CSV content has no header row"
        raise ValueError(msg)
    rows: list[dict[str, str]] = []
    for index, record in enumerate(reader, start=1):
        if None in record:  # more cells than headers
            msg = f"row {index} has more cells than header columns"
            raise ValueError(msg)
        rows.append({str(k): ("" if v is None else str(v)) for k, v in record.items()})
    return tuple(rows)


class IntakeAdapter:
    """Batch → per-row ``capture_external`` + recorded scan; quarantine on batch faults."""

    def __init__(self, *, lifecycle: LearningLifecycleService) -> None:
        self._lifecycle = lifecycle

    def ingest(
        self,
        tenant_id: UUID,
        *,
        expectations: IntakeExpectations,
        format: str,
        content: str,
    ) -> IntakeReport:
        if len(content.encode("utf-8")) > MAX_CONTENT_BYTES:
            return IntakeReport(
                rows=0,
                quarantined=True,
                quarantine_reason=f"content exceeds {MAX_CONTENT_BYTES} bytes",
                format=format,
            )
        try:
            rows = parse_intake_rows(format, content)
        except ValueError as exc:
            return IntakeReport(rows=0, quarantined=True, quarantine_reason=str(exc), format=format)
        if len(rows) > expectations.max_rows:
            limit = expectations.max_rows
            return IntakeReport(
                rows=len(rows),
                quarantined=True,
                quarantine_reason=f"batch has {len(rows)} rows; max_rows is {limit}",
                format=format,
            )
        columns_seen: list[str] = []
        for row in rows:
            for column in row:
                if column not in columns_seen:
                    columns_seen.append(column)

        admitted: list[AdmittedRow] = []
        refused: list[RefusedRow] = []
        for index, row in enumerate(rows, start=1):
            missing = [c for c in expectations.required_columns if not row.get(c, "").strip()]
            if missing:
                refused.append(
                    RefusedRow(
                        row=index, reason=f"missing required column(s): {', '.join(missing)}"
                    )
                )
                continue
            knowledge_key = row[expectations.key_column].strip()
            knowledge_value: JsonObject = {
                column: value for column, value in row.items() if column != expectations.key_column
            }
            sample = self._lifecycle.capture_external(
                tenant_id, knowledge_key=knowledge_key, knowledge_value=knowledge_value
            )
            # Record the deterministic scan NOW (pure report; state untouched).
            report = self._lifecycle.sanitize(tenant_id, sample.id)
            admitted.append(
                AdmittedRow(
                    row=index,
                    sample_id=str(sample.id),
                    knowledge_key=knowledge_key,
                    scan_clean=report.clean,
                    findings=tuple(f.as_json() for f in report.findings),
                )
            )
        return IntakeReport(
            rows=len(rows),
            admitted=tuple(admitted),
            refused=tuple(refused),
            format=format,
            columns_seen=tuple(columns_seen),
        )
