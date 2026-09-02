"""Skill source catalog — the 41 §16 import-source list as governed DATA.

WHAT THIS IS
------------
41 §16 names three import sources; the import pipeline (T-IMPL-062)
admits a ``source_url`` only against that allowlist. Until now the list
was constructor DATA frozen at composition. This module makes it a
first-class, ordered, classified catalog that the admin surface can
replace atomically (SET_SKILL_SOURCES — 21 §4 'Skills: import' control
row: WHERE imports may come from is admin-governed configuration):

- ORDERED: list position is priority (index 0 = first consulted /
  most-trusted). No doc defines a numeric priority scheme; order-as-
  priority is the recorded minimal reading.
- CLASSIFIED: each entry carries a ``kind`` derived from its URL —
  ``git_repository`` (github.com hosts) or ``web_catalog`` (anything
  else). Recorded derivation, verifiable from the URL itself; nothing
  else is guessed about the source.
- ENABLE/DISABLE per entry: a disabled source stays LISTED (its history
  and priority are preserved) but stops admitting imports — the same
  status-vs-existence split every registry in this codebase uses.

WHAT THIS IS NOT
----------------
- NOT a fetcher: 14 §3 verbatim — "External sources are references, not
  runtime dependencies." The catalog never dereferences a URL.
- NOT a bypass: the SkillImportService keeps its own prefix-admission
  rule; the catalog only SUPPLIES the live prefix list (one source of
  truth, no parallel state — P2).

The default catalog seeds the three 41 §16 URLs verbatim, in the order
the doc lists them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Lock

from core.skills.importing import IMPORT_SOURCES


class SkillSourceKind(StrEnum):
    """Source classification — derived from the URL, never guessed."""

    GIT_REPOSITORY = "git_repository"
    WEB_CATALOG = "web_catalog"


class InvalidSourceUrl(Exception):
    """A source URL that fails admission (scheme/emptiness/duplicate)."""


def classify_source(url: str) -> SkillSourceKind:
    """Derive the kind from the URL host (recorded rule: github ⇒ git)."""
    if url.startswith("https://github.com/"):
        return SkillSourceKind.GIT_REPOSITORY
    return SkillSourceKind.WEB_CATALOG


@dataclass(frozen=True)
class SkillSourceEntry:
    """One catalog row: URL + derived kind + admin-controlled enablement.

    Priority IS list position in the catalog — deliberately kept off the
    row so it cannot drift from the order.
    """

    url: str
    kind: SkillSourceKind
    enabled: bool = True


def _admit_url(url: str) -> str:
    """Admission for one URL: https-only, non-empty host beyond scheme."""
    if not isinstance(url, str) or not url:
        raise InvalidSourceUrl("source url must be a non-empty string")
    if not url.startswith("https://"):
        raise InvalidSourceUrl(f"source url must use https: {url!r}")
    if len(url) <= len("https://") + 1:
        raise InvalidSourceUrl(f"source url has no host: {url!r}")
    return url


def _build_entries(
    urls: list[str], *, disabled: frozenset[str] = frozenset()
) -> tuple[SkillSourceEntry, ...]:
    seen: set[str] = set()
    entries: list[SkillSourceEntry] = []
    for url in urls:
        admitted = _admit_url(url)
        if admitted in seen:
            raise InvalidSourceUrl(f"duplicate source url: {admitted!r}")
        seen.add(admitted)
        entries.append(
            SkillSourceEntry(
                url=admitted,
                kind=classify_source(admitted),
                enabled=admitted not in disabled,
            )
        )
    return tuple(entries)


class SkillSourceCatalog:
    """Ordered, mutable-by-admin-only catalog of import sources.

    Thread-safe replace/read (the admin surface publishes from request
    handlers; the import service reads on every import). All mutation
    goes through :meth:`set_sources` — the SET_SKILL_SOURCES publish path.
    """

    def __init__(self, urls: list[str] | None = None) -> None:
        seed = urls if urls is not None else list(IMPORT_SOURCES)
        self._lock = Lock()
        self._entries = _build_entries(seed)

    # --- reads -----------------------------------------------------------------

    def entries(self) -> tuple[SkillSourceEntry, ...]:
        """All rows in priority order (disabled rows included — visible)."""
        with self._lock:
            return self._entries

    def allowed_prefixes(self) -> tuple[str, ...]:
        """ENABLED source URLs, priority order — the live import allowlist."""
        with self._lock:
            return tuple(e.url for e in self._entries if e.enabled)

    # --- the one mutation (admin publish path) ----------------------------------

    def set_sources(
        self, urls: list[str], *, disabled: list[str] | None = None
    ) -> tuple[SkillSourceEntry, ...]:
        """Atomically replace the catalog; returns the PREVIOUS entries.

        ``urls`` is the complete new list in priority order (this is a
        REPLACE, not a merge — the admin change payload is the whole
        desired state, same posture as SET_ROUTING_WEIGHTS). ``disabled``
        names urls that stay listed but stop admitting imports; a disabled
        url not present in ``urls`` is a contradiction and refuses.
        """
        disabled_set = frozenset(disabled or ())
        unknown = disabled_set - set(urls)
        if unknown:
            raise InvalidSourceUrl(
                "disabled urls must appear in the source list: " + ", ".join(sorted(unknown))
            )
        new_entries = _build_entries(list(urls), disabled=disabled_set)
        with self._lock:
            previous = self._entries
            self._entries = new_entries
        return previous

    def restore(self, entries: tuple[SkillSourceEntry, ...]) -> None:
        """Rollback path: restore a previously captured snapshot verbatim."""
        with self._lock:
            self._entries = entries
