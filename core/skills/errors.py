"""Skill import/lifecycle errors (closed, minimal set — T-IMPL-062).

Same explainable-denial posture as core/roles (11 §14): every refusal
names the violated rule, never a silent skip. 14 §9 forbidden list binds:
"Imported skill becomes active without review" — the lifecycle errors are
how that rule refuses loudly.
"""

from __future__ import annotations


class SkillImportError(Exception):
    """Base class for skill import / lifecycle failures."""


class UnknownImportSource(SkillImportError):
    """The declared source is not on the import-source allowlist.

    Deny-by-default (41 §1 rule 9): sources are configuration DATA
    (default = the 41 §16 verbatim list); anything else is refused.
    """

    def __init__(self, source_url: str) -> None:
        self.source_url = source_url
        super().__init__(f"unknown import source: {source_url}")


class ChecksumMismatch(SkillImportError):
    """Imported content does not match its declared checksum (14 §10)."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"checksum mismatch: expected {expected}, got {actual}")


class NotAnImportedSkill(SkillImportError):
    """The import lifecycle governs source=imported only (14 §3).

    Local skills never traverse the import pipeline — their creation path
    is a separate concern; applying import steps to them is a caller error.
    """

    def __init__(self, skill_id: object, source: str) -> None:
        self.source = source
        super().__init__(f"not an imported skill: {skill_id} (source={source})")


class InvalidLifecycleStep(SkillImportError):
    """The step's required predecessor state does not hold (14 §3 order).

    One step at a time, in pipeline order — this is what makes 14 §9
    "Imported skill becomes active without review" structurally impossible.
    """

    def __init__(self, skill_id: object, current: str, step: str) -> None:
        self.current = current
        self.step = step
        super().__init__(
            f"invalid lifecycle step for {skill_id}: cannot {step} from status={current}"
        )


class ScanFindingsBlock(SkillImportError):
    """The scan reported findings — the skill is blocked (14 §10).

    "malicious skill blocked": a non-empty findings list refuses the
    scanned transition; the skill never progresses toward active.
    """

    def __init__(self, skill_id: object, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__(
            f"scan blocked skill {skill_id}: {len(findings)} finding(s): " + "; ".join(findings)
        )


class MissingProvenance(SkillImportError):
    """An imported skill is missing a required provenance field (14 §3).

    Enforces the contract-layer promise recorded on SkillProvenance:
    "the (later) import machinery enforces presence for source=imported".
    """

    def __init__(self, skill_id: object, field: str) -> None:
        self.field = field
        super().__init__(f"imported skill {skill_id} missing provenance: {field}")
