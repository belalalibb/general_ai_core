"""Deterministic learning-sample sanitizer — Phase 3 / R161 (22 §8, §12).

22 §12 names the test verbatim: "sanitization removes secrets". Until now
the lifecycle's sanitization step was an explicit reviewed ACT only
(``mark_sanitized(passed=...)``) — honest, but a human toggle with no
machine check behind it. The platform ALREADY owns the credential
patterns (``core/memory/memory.py`` screens every memory write with
them), yet they fired only at GOLD promotion time — the LAST step — so
a poisoned sample travelled the whole pipeline before failing loud.

This module moves the SAME class of check to where the spec puts
sanitization: before evaluation. It builds nothing new in spirit — the
key indicators and value patterns mirror the memory screen — and adds
exactly one honest capability: a *finding* names WHERE (JSON path) and
WHAT KIND (label) matched, never the matched text itself (a sanitizer
that echoes the secret it found is a leak).

Recorded decisions:

- DETERMINISTIC + PURE: no I/O, no model call, same input ⇒ same report.
- FINDINGS, NOT REDACTION: the sanitizer REPORTS; it never rewrites the
  sample. A reviewer decides (the explicit act stays) — but the act now
  carries the machine report as evidence, and ``passed=True`` over
  unresolved findings is REFUSED by the lifecycle (deny-by-default).
- NO SECRET ECHO: ``SanitizationFinding`` carries path + label + a
  fixed-width fingerprint of the match (sha256 prefix) so two reports
  can be compared without either revealing content.
- CLOSED LABEL SET: the labels are data (``SECRET_LABELS``) — a UI or
  test can enumerate them; nothing else can be reported.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from core.contracts.base import JsonObject

__all__ = [
    "SECRET_LABELS",
    "SanitizationFinding",
    "SanitizationReport",
    "sanitize_knowledge",
]

# Key substrings indicating credential material (mirrors the 13 §7 memory
# screen — one vocabulary, two enforcement points).
_KEY_INDICATORS: tuple[str, ...] = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "private_key",
    "credential",
    "client_secret",
)

_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9\-_.~+/]{16,}", re.IGNORECASE)),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt_like_token", re.compile(r"\beyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.")),
    ("opaque_provider_token", re.compile(r"\b(?:sk|pk|ghp|gho|xoxb)-[A-Za-z0-9\-_]{16,}\b")),
    ("github_pat", re.compile(r"\bghp_[0-9A-Za-z]{36}\b")),
)

#: Closed set of finding labels (data — enumerable by consumers).
SECRET_LABELS: tuple[str, ...] = ("credential_key",) + tuple(label for label, _ in _VALUE_PATTERNS)


@dataclass(frozen=True)
class SanitizationFinding:
    """One secret-like hit: WHERE and WHAT KIND — never the text itself."""

    path: str  # JSON path inside the knowledge value, or "$key" for the key
    label: str  # one of SECRET_LABELS
    fingerprint: str  # sha256 prefix of the matched text (comparable, non-revealing)

    def as_json(self) -> JsonObject:
        return {"path": self.path, "label": self.label, "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class SanitizationReport:
    """Deterministic verdict over one sample's knowledge (key + value)."""

    findings: tuple[SanitizationFinding, ...]
    scanned_paths: int

    @property
    def clean(self) -> bool:
        return not self.findings

    def as_json(self) -> JsonObject:
        return {
            "clean": self.clean,
            "scanned_paths": self.scanned_paths,
            "findings": [f.as_json() for f in self.findings],
        }


def _fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _walk(value: object, path: str, out: list[tuple[str, str]]) -> None:
    """Flatten a JSON value into (path, string) leaves; keys are leaves too."""
    if isinstance(value, dict):
        for k, v in value.items():
            key_path = f"{path}.{k}" if path else str(k)
            out.append((f"{key_path}#key", str(k)))
            _walk(v, key_path, out)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _walk(v, f"{path}[{i}]", out)
    elif isinstance(value, str):
        out.append((path or "$", value))
    elif value is None or isinstance(value, bool | int | float):
        out.append((path or "$", json.dumps(value)))


def sanitize_knowledge(knowledge_key: str, knowledge_value: JsonObject) -> SanitizationReport:
    """Scan key + value for credential material; report findings by path.

    Pure and deterministic: the report is a function of its inputs only.
    """
    leaves: list[tuple[str, str]] = [("$key", knowledge_key)]
    _walk(knowledge_value, "", leaves)
    findings: list[SanitizationFinding] = []
    for path, text in leaves:
        lowered = text.lower()
        if path.endswith("#key") or path == "$key":
            for indicator in _KEY_INDICATORS:
                if indicator in lowered:
                    findings.append(
                        SanitizationFinding(
                            path=path, label="credential_key", fingerprint=_fingerprint(text)
                        )
                    )
                    break
        for label, pattern in _VALUE_PATTERNS:
            match = pattern.search(text)
            if match is not None:
                findings.append(
                    SanitizationFinding(
                        path=path, label=label, fingerprint=_fingerprint(match.group(0))
                    )
                )
    return SanitizationReport(findings=tuple(findings), scanned_paths=len(leaves))
