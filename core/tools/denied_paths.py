"""Hardened path denylist for the dev-agent surface (R172 C1).

Superset of ``core.tools.source_reader.DEFAULT_DENIED_PATTERNS`` covering the
27 EXPECT_DENIED rows of ``evidence/r170/denylist_probe.txt`` plus the classes
mandated by the R172 directive (verification gate, SSH/cloud/GPG homes, key
stores, system credential files, accounts/cookies/tokens/password names).

Matching is plain ``fnmatch`` on the relative POSIX path, exactly as
``SourceReader._denied`` / ``SourceWriter._denied`` apply it, so this module
introduces no new matching semantics — it only widens the list. It is wired at
``apps.agent_dev.surface.build_dev_surface`` composition; the bare primitives
keep their defaults.

NOTE: the explicit case variants (``.ENV*`` / ``.Env*``) are a patch —
enumeration cannot cover every spelling; the proper fix is path normalisation
in the reader/writer admission check (R172 C4).
"""

from __future__ import annotations

from fnmatch import fnmatch

from core.tools.source_reader import DEFAULT_DENIED_PATTERNS

__all__ = ["DENIED_PATH_PATTERNS", "HARDENED_PATTERNS", "is_denied_path"]


def _anywhere(*names: str) -> tuple[str, ...]:
    """Root-level and nested variants for each bare name/glob."""
    out: list[str] = []
    for n in names:
        out.append(n)
        out.append(f"*/{n}")
    return tuple(out)


HARDENED_PATTERNS: tuple[str, ...] = (
    # verification gate — the agent must not read or edit its own gate
    "engineering/verification",
    "engineering/verification/*",
    *_anywhere("green_manifest.json"),
    # sensitive home directories
    *_anywhere(".ssh", ".ssh/*", ".aws", ".aws/*", ".kube", ".kube/*", ".gnupg", ".gnupg/*"),
    # ssh material by name
    *_anywhere("id_*", "authorized_keys", "known_hosts"),
    # key stores / cert bundles
    "*.pfx",
    "*.asc",
    "*.jks",
    "*.keystore",
    "*.pkcs12",
    # system / tool credential files
    *_anywhere("passwd", "shadow", ".netrc", ".pgpass"),
    # credential-bearing names (directive-mandated; see notes on collateral)
    "*accounts*",
    "*cookies*",
    "*tokens*",
    "*password*",
    # case variants of .env — patch only; normalisation lands in C4
    *_anywhere(".ENV", ".ENV.*", ".Env", ".Env.*"),
)


def _dedupe(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for g in groups:
        for p in g:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return tuple(out)


#: Full hardened denylist: reader defaults first, then the hardened additions.
DENIED_PATH_PATTERNS: tuple[str, ...] = _dedupe(DEFAULT_DENIED_PATTERNS, HARDENED_PATTERNS)


def is_denied_path(rel_posix: str, patterns: tuple[str, ...] = DENIED_PATH_PATTERNS) -> bool:
    """True when ``rel_posix`` matches any denied pattern (fnmatch semantics)."""
    return any(fnmatch(rel_posix, pattern) for pattern in patterns)
