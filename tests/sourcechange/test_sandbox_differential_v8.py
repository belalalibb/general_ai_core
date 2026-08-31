"""V8 chunk 4 — sandbox port + hermetic binding + differential verifier.

Acceptance-criteria mapping (this chunk's share):

- criterion 2 (sandbox isolation is structural) -> the port surface pin:
  ONE method, no write/remote/secret parameter anywhere in the interface;
  the hermetic binding's constructor takes nothing.
- criterion 3 (synthetic/sanitized state) -> the binding holds no state at
  all; only snapshot bytes exist inside a run.
- criterion 4 (real execution works inside the sandbox) ->
  python_syntax_valid genuinely compiles snapshot code and genuinely
  fails on a syntax error.
- criterion 5 (deterministic differential verification) -> same-input
  reports are canonical-JSON identical; a nondeterministic sandbox is
  REFUSED (NonDeterministicVerification), never half-trusted.
- criterion 6 substrate -> base-pass/patched-fail = REGRESSION verdict.
"""

from __future__ import annotations

import inspect

import pytest

from core.sourcechange import (
    SOURCE_VERIFICATION_CHECKS,
    DifferentialVerdict,
    DifferentialVerifier,
    HermeticSandbox,
    MalformedPatch,
    NonDeterministicVerification,
    SandboxPort,
    SourceCheck,
    SourceSnapshot,
    VerificationReport,
    VerificationSuite,
)

GOOD = SourceSnapshot.from_files(
    {"src/app.py": b"print('ok')\n", "README.md": b"# demo\n"}
)
BROKEN = SourceSnapshot.from_files(
    {"src/app.py": b"def broken(:\n", "README.md": b"# demo\n"}
)
DEFAULT_SUITE = VerificationSuite(name="default", checks=SOURCE_VERIFICATION_CHECKS)


# --- Suite shape (P7) -----------------------------------------------------------------


def test_suite_refuses_empty_and_duplicate_checks() -> None:
    with pytest.raises(MalformedPatch, match="must contain checks"):
        VerificationSuite(name="empty", checks=())
    check = SourceCheck(name="x", predicate=lambda s: True)
    with pytest.raises(MalformedPatch, match="duplicate check name"):
        VerificationSuite(name="dup", checks=(check, check))


# --- Structural isolation (criterion 2) -----------------------------------------------


def test_sandbox_port_surface_is_one_method_no_capability_params() -> None:
    """The port's ENTIRE surface: run_verification(snapshot, suite).

    No parameter through which a write target, remote, credential, or
    environment could be requested — pinned by introspection so any
    future widening of the interface fails this test consciously."""
    members = [
        name
        for name, value in vars(SandboxPort).items()
        if not name.startswith("_") and callable(value)
    ]
    assert members == ["run_verification"]
    signature = inspect.signature(HermeticSandbox.run_verification)
    assert list(signature.parameters) == ["self", "snapshot", "suite"]


def test_hermetic_sandbox_constructor_takes_nothing() -> None:
    """Criterion 3 structurally: nothing real can be injected, so nothing
    real exists to leak."""
    signature = inspect.signature(HermeticSandbox)
    assert list(signature.parameters) == []
    HermeticSandbox()  # constructible with nothing — and only nothing
    with pytest.raises(TypeError):
        HermeticSandbox("some/real/path")  # type: ignore[call-arg]


def test_sandbox_module_imports_no_io_machinery() -> None:
    import sys

    module = sys.modules["core.sourcechange.sandbox"]
    names = set(vars(module))
    for forbidden in ("os", "subprocess", "socket", "urllib", "http"):
        assert forbidden not in names


# --- Real execution inside the sandbox (criterion 4) -----------------------------------


def test_python_syntax_check_really_compiles() -> None:
    good_report = HermeticSandbox().run_verification(GOOD, DEFAULT_SUITE)
    broken_report = HermeticSandbox().run_verification(BROKEN, DEFAULT_SUITE)
    by_name_good = {r.name: r.passed for r in good_report.results}
    by_name_broken = {r.name: r.passed for r in broken_report.results}
    assert by_name_good["python_syntax_valid"] is True
    assert by_name_broken["python_syntax_valid"] is False
    assert good_report.passed is True
    assert broken_report.passed is False


def test_tampered_snapshot_refuses_verification_loudly() -> None:
    forged = SourceSnapshot(snapshot_id="0" * 64, files=GOOD.files)
    report = HermeticSandbox().run_verification(forged, DEFAULT_SUITE)
    assert report.passed is False
    (result,) = report.results
    assert result.name == "snapshot_integrity"
    assert "content-address" in result.detail


def test_broken_check_is_a_failing_check_not_an_error() -> None:
    def _explodes(snapshot: SourceSnapshot) -> bool:
        raise RuntimeError("check machinery broke")

    suite = VerificationSuite(
        name="broken", checks=(SourceCheck(name="explodes", predicate=_explodes),)
    )
    report = HermeticSandbox().run_verification(GOOD, suite)
    (result,) = report.results
    assert result.passed is False
    assert "RuntimeError" in result.detail  # named, honest (P6)


# --- Determinism (criterion 5) ----------------------------------------------------------


def test_verification_is_deterministic_canonical_json() -> None:
    sandbox = HermeticSandbox()
    first = sandbox.run_verification(GOOD, DEFAULT_SUITE)
    second = sandbox.run_verification(GOOD, DEFAULT_SUITE)
    assert first.canonical_json() == second.canonical_json()


class _FlakySandbox:
    """A sandbox whose reports differ run-to-run — must be REFUSED."""

    def __init__(self) -> None:
        self._runs = 0

    def run_verification(
        self, snapshot: SourceSnapshot, suite: VerificationSuite
    ) -> VerificationReport:
        self._runs += 1
        from core.sourcechange.sandbox import CheckResult

        return VerificationReport(
            snapshot_id=snapshot.snapshot_id,
            suite_name=suite.name,
            results=(
                CheckResult(name="flaky", passed=self._runs % 2 == 1, detail=""),
            ),
        )


def test_nondeterministic_sandbox_is_refused_never_half_trusted() -> None:
    verifier = DifferentialVerifier(sandbox=_FlakySandbox())
    with pytest.raises(NonDeterministicVerification):
        verifier.verify(GOOD, BROKEN, DEFAULT_SUITE)


# --- Differential grading (criteria 5 + 6 substrate) -------------------------------------


def test_differential_pass_when_patched_holds_everything() -> None:
    report = DifferentialVerifier(HermeticSandbox()).verify(
        GOOD,
        SourceSnapshot.from_files({"src/app.py": b"print('v2')\n"}),
        DEFAULT_SUITE,
    )
    assert report.verdict is DifferentialVerdict.PASS
    assert report.regressions == ()


def test_differential_regression_base_pass_patched_fail() -> None:
    report = DifferentialVerifier(HermeticSandbox()).verify(GOOD, BROKEN, DEFAULT_SUITE)
    assert report.verdict is DifferentialVerdict.REGRESSION
    assert report.regressions == ("python_syntax_valid",)
    # full evidence carried, both sides (criterion 11 substrate)
    assert report.base_report.passed is True
    assert report.patched_report.passed is False


def test_differential_improvement_is_named_not_hidden() -> None:
    report = DifferentialVerifier(HermeticSandbox()).verify(BROKEN, GOOD, DEFAULT_SUITE)
    assert report.verdict is DifferentialVerdict.PASS
    assert report.improvements == ("python_syntax_valid",)


def test_differential_failed_on_patched_without_regression() -> None:
    """A check failing on BOTH sides is not a regression — but a failing
    patched snapshot still cannot claim PASS (honest middle verdict)."""
    report = DifferentialVerifier(HermeticSandbox()).verify(
        BROKEN,
        SourceSnapshot.from_files({"src/app.py": b"also broken(:\n"}),
        DEFAULT_SUITE,
    )
    assert report.verdict is DifferentialVerdict.FAILED_ON_PATCHED
    assert report.regressions == ()


def test_differential_is_reproducible_end_to_end() -> None:
    verifier = DifferentialVerifier(HermeticSandbox())
    first = verifier.verify(GOOD, BROKEN, DEFAULT_SUITE)
    second = verifier.verify(GOOD, BROKEN, DEFAULT_SUITE)
    assert first.verdict is second.verdict
    assert first.regressions == second.regressions
    assert first.base_report.canonical_json() == second.base_report.canonical_json()
    assert (
        first.patched_report.canonical_json()
        == second.patched_report.canonical_json()
    )
