"""Ephemeral verification sandbox + differential verifier (ADR-0009 / V8).

STRUCTURAL INCAPABILITY (the operator's binding constraint, recorded):
:class:`SandboxPort` exposes exactly ONE operation —
``run_verification(snapshot, suite) -> VerificationReport``. The
interface has NO parameter or method through which authoritative writes,
remote pushes, or secret resolution could even be requested. The
capability is absent from the TYPE, not forbidden by a check (the
AA-2/AA-3 registry precedent). Tests pin the port surface.

The hermetic binding (:class:`HermeticSandbox`) evaluates checks over the
snapshot's OWN bytes only — its constructor takes nothing, so there is
nothing real to leak into it (criterion 3: synthetic/sanitized state is
the only state that exists). "Real execution inside the sandbox"
(criterion 4) is honest and bounded: the built-in ``python_syntax_valid``
check genuinely COMPILES every ``*.py`` file in the snapshot with the
CPython compiler — real work over snapshot bytes, zero IO.

Check machinery follows the R121 recorded precedent: the platform's
``DeterministicCheck`` binds to execution output, so source verification
defines its OWN frozen check shape over snapshots rather than misusing
that contract — same closed-set discipline, correct binding.

:class:`DifferentialVerifier` (criterion 5): runs the SAME suite on the
base and the patched snapshot, twice each (the R121 determinism proof —
non-reproducible verification refuses itself), and grades the delta with
a closed verdict set. A check passing on base and failing on patched is a
REGRESSION; regressions force the blocking verdict (criterion 6 feeds the
lifecycle's FAILED_VERIFICATION in chunk 5).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from core.sourcechange.errors import MalformedPatch
from core.sourcechange.snapshot import SourceSnapshot

__all__ = [
    "SOURCE_VERIFICATION_CHECKS",
    "CheckResult",
    "DifferentialReport",
    "DifferentialVerdict",
    "DifferentialVerifier",
    "HermeticSandbox",
    "NonDeterministicVerification",
    "SandboxPort",
    "SourceCheck",
    "VerificationReport",
    "VerificationSuite",
]


@dataclass(frozen=True)
class SourceCheck:
    """One named, pure check over a source snapshot (data, not machinery)."""

    name: str
    predicate: Callable[[SourceSnapshot], bool]


@dataclass(frozen=True)
class VerificationSuite:
    """A closed, duplicate-free, non-empty tuple of checks.

    An empty suite proves nothing and is refused at construction — the
    same posture as the chunk-3 scenario rule (a checkless scenario
    proves nothing).
    """

    name: str
    checks: tuple[SourceCheck, ...]

    def __post_init__(self) -> None:
        if not self.checks:
            raise MalformedPatch("a verification suite must contain checks")
        seen: set[str] = set()
        for check in self.checks:
            if check.name in seen:
                raise MalformedPatch(f"duplicate check name {check.name!r}")
            seen.add(check.name)


@dataclass(frozen=True)
class CheckResult:
    """One check verdict — pass/fail plus an honest detail string.

    A predicate that RAISES is recorded as ``passed=False`` with the
    exception named in ``detail`` (P6: a broken check is a failing check,
    never a silent skip and never a transport error).
    """

    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class VerificationReport:
    """The complete result of one suite run over one snapshot."""

    snapshot_id: str
    suite_name: str
    results: tuple[CheckResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def canonical_json(self) -> str:
        """Canonical serialization — the determinism-comparison instrument."""
        return json.dumps(
            {
                "snapshot_id": self.snapshot_id,
                "suite_name": self.suite_name,
                "results": [
                    {"name": r.name, "passed": r.passed, "detail": r.detail} for r in self.results
                ],
            },
            sort_keys=True,
        )


class SandboxPort(Protocol):
    """The ONLY execution surface for proposed source (ADR-0009).

    One method. No write target, no remote, no secret parameter — the
    §14-relevant capabilities are structurally absent from the interface.
    Real bindings (containers, workers) are an activation-gate concern;
    they implement this same port later (criterion 12).
    """

    def run_verification(
        self, snapshot: SourceSnapshot, suite: VerificationSuite
    ) -> VerificationReport: ...


class HermeticSandbox:
    """In-memory sandbox binding — evaluates checks over snapshot bytes only.

    The constructor takes NOTHING: no paths, no environment, no secret
    manager. What the sandbox cannot hold it cannot leak (criterion 3
    structurally). Each run verifies the snapshot's content-address first
    — a tampered snapshot refuses verification loudly rather than grading
    forged bytes.
    """

    def run_verification(
        self, snapshot: SourceSnapshot, suite: VerificationSuite
    ) -> VerificationReport:
        results: list[CheckResult] = []
        if not snapshot.verify_integrity():
            results.append(
                CheckResult(
                    name="snapshot_integrity",
                    passed=False,
                    detail="snapshot failed content-address verification",
                )
            )
            return VerificationReport(
                snapshot_id=snapshot.snapshot_id,
                suite_name=suite.name,
                results=tuple(results),
            )
        for check in suite.checks:
            try:
                passed = bool(check.predicate(snapshot))
                detail = "" if passed else "predicate returned False"
            except Exception as exc:  # noqa: BLE001 - broken check = failing check
                passed = False
                detail = f"check raised: {type(exc).__name__}: {exc}"
            results.append(CheckResult(name=check.name, passed=passed, detail=detail))
        return VerificationReport(
            snapshot_id=snapshot.snapshot_id,
            suite_name=suite.name,
            results=tuple(results),
        )


# --- Built-in source checks (data, closed default suite) ---------------------------


def _non_empty_snapshot(snapshot: SourceSnapshot) -> bool:
    return len(snapshot.files) > 0


def _manifest_integrity(snapshot: SourceSnapshot) -> bool:
    return snapshot.verify_integrity()


def _python_syntax_valid(snapshot: SourceSnapshot) -> bool:
    """REAL execution inside the sandbox (criterion 4, honest scope):
    compiles every ``*.py`` file with the CPython compiler. Real work,
    deterministic, zero IO — and a syntax error is a real failure."""
    for path, content in snapshot.files.items():
        if path.endswith(".py"):
            try:
                compile(content, path, "exec")
            except SyntaxError:
                return False
    return True


SOURCE_VERIFICATION_CHECKS: tuple[SourceCheck, ...] = (
    SourceCheck(name="non_empty_snapshot", predicate=_non_empty_snapshot),
    SourceCheck(name="manifest_integrity", predicate=_manifest_integrity),
    SourceCheck(name="python_syntax_valid", predicate=_python_syntax_valid),
)


# --- Differential verification (criterion 5) ----------------------------------------


class NonDeterministicVerification(Exception):
    """The same suite over the same snapshot produced different reports.

    A verification that cannot reproduce itself proves nothing — it is
    refused rather than half-trusted (P6)."""

    def __init__(self, snapshot_id: str) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"verification over snapshot {snapshot_id!r} is not deterministic")


class DifferentialVerdict(StrEnum):
    """Closed verdict set — chunk 5 promotes ONLY on PASS."""

    PASS = "pass"
    REGRESSION = "regression"
    FAILED_ON_PATCHED = "failed_on_patched"


@dataclass(frozen=True)
class DifferentialReport:
    """Base-vs-patched evidence: both full reports plus the graded delta."""

    base_report: VerificationReport
    patched_report: VerificationReport
    regressions: tuple[str, ...]
    improvements: tuple[str, ...]
    verdict: DifferentialVerdict


class DifferentialVerifier:
    """Runs the SAME suite on base and patched snapshots and grades the delta.

    Determinism is PROVEN per run (R121 pattern): each snapshot is
    verified twice and the canonical JSON must match, else
    :class:`NonDeterministicVerification` — an irreproducible
    verification never reaches a verdict.
    """

    def __init__(self, sandbox: SandboxPort) -> None:
        self._sandbox = sandbox

    def _verified_twice(
        self, snapshot: SourceSnapshot, suite: VerificationSuite
    ) -> VerificationReport:
        first = self._sandbox.run_verification(snapshot, suite)
        second = self._sandbox.run_verification(snapshot, suite)
        if first.canonical_json() != second.canonical_json():
            raise NonDeterministicVerification(snapshot.snapshot_id)
        return first

    def verify(
        self,
        base: SourceSnapshot,
        patched: SourceSnapshot,
        suite: VerificationSuite,
    ) -> DifferentialReport:
        base_report = self._verified_twice(base, suite)
        patched_report = self._verified_twice(patched, suite)
        base_by_name = {r.name: r.passed for r in base_report.results}
        patched_by_name = {r.name: r.passed for r in patched_report.results}
        regressions = tuple(
            name
            for name in sorted(base_by_name)
            if base_by_name[name] and not patched_by_name.get(name, False)
        )
        improvements = tuple(
            name
            for name in sorted(base_by_name)
            if not base_by_name[name] and patched_by_name.get(name, False)
        )
        if regressions:
            verdict = DifferentialVerdict.REGRESSION
        elif not patched_report.passed:
            verdict = DifferentialVerdict.FAILED_ON_PATCHED
        else:
            verdict = DifferentialVerdict.PASS
        return DifferentialReport(
            base_report=base_report,
            patched_report=patched_report,
            regressions=regressions,
            improvements=improvements,
            verdict=verdict,
        )
