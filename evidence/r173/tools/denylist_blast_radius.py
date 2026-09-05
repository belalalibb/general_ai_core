#!/usr/bin/env python3
"""R173 §1.5 / §5 — denylist blast radius over the TRACKED tree, three forms.

For every path in ``git ls-files`` decide admission under the three deny
forms that exist in code today:

  form A  DEFAULT_DENIED_PATTERNS   13 globs — apps/composition/runtime.py::_source_reader
                                               (platform agent source_* tools)
  form B  DENIED_PATH_PATTERNS      64 globs — R172 hardened superset, composed only by
                                               apps/agent_dev/surface.py
  form C  is_denied(path, B)        B + normalisation (NFKC, invisibles, ADS suffix,
                                               trailing dot/space, casefold) — the check
                                               the reader actually runs

Output (R173_BR_OUT dir): summary.json, denied_A.txt, denied_B.txt,
denied_C_only.txt, collateral_B.txt (form-B denials that are ordinary
source/test/doc files, i.e. the operational cost of B).

Pure read-only measurement; no server, no secrets, no file contents read.
"""

from __future__ import annotations

import collections
import json
import os
import pathlib
import subprocess
import sys
from fnmatch import fnmatch

sys.path.insert(0, os.getcwd())
from core.tools.denied_paths import DENIED_PATH_PATTERNS  # noqa: E402
from core.tools.source_reader import DEFAULT_DENIED_PATTERNS, is_denied  # noqa: E402

OUT = pathlib.Path(os.environ.get("R173_BR_OUT", "evidence/r173/16_denylist_blast_radius"))
OUT.mkdir(parents=True, exist_ok=True)

raw = subprocess.run(["git", "ls-files", "-z"], check=True, capture_output=True).stdout
tracked = sorted(p for p in raw.decode("utf-8", "surrogateescape").split("\0") if p)


def hits(path: str, patterns: tuple[str, ...]) -> list[str]:
    return [pat for pat in patterns if fnmatch(path, pat)]


CRED_MARKERS = (".env", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".asc", ".netrc", ".pgpass",
                "id_", "authorized_keys", "known_hosts", ".ssh", ".aws", ".kube", ".gnupg", ".git/", ".git-credentials")


def looks_like_credential_material(path: str) -> bool:
    low = path.lower()
    return any(m in low for m in CRED_MARKERS)


denied_A: list[str] = []
denied_B: list[str] = []
denied_C_only: list[str] = []
pattern_hits_A: collections.Counter[str] = collections.Counter()
pattern_hits_B: collections.Counter[str] = collections.Counter()
per_dir_B: collections.Counter[str] = collections.Counter()
collateral_B: list[tuple[str, list[str]]] = []

for path in tracked:
    a = hits(path, DEFAULT_DENIED_PATTERNS)
    b = hits(path, DENIED_PATH_PATTERNS)
    c = is_denied(path, DENIED_PATH_PATTERNS)
    if a:
        denied_A.append(path)
        pattern_hits_A.update(a)
    if b:
        denied_B.append(path)
        pattern_hits_B.update(b)
        per_dir_B[path.split("/", 1)[0] if "/" in path else "<root>"] += 1
        if not looks_like_credential_material(path):
            collateral_B.append((path, b))
    if c and not b:
        denied_C_only.append(path)

summary = {
    "head": subprocess.run(["git", "rev-parse", "--short", "HEAD"], check=True, capture_output=True, text=True).stdout.strip(),
    "tracked_files": len(tracked),
    "forms": {
        "A_default_runtime": {
            "pattern_count": len(DEFAULT_DENIED_PATTERNS),
            "denied": len(denied_A),
            "pattern_hits": dict(pattern_hits_A),
            "composed_by": "apps/composition/runtime.py::_source_reader (platform agent source_* tools)",
        },
        "B_hardened_agent_dev": {
            "pattern_count": len(DENIED_PATH_PATTERNS),
            "denied": len(denied_B),
            "pattern_hits": dict(pattern_hits_B),
            "per_top_dir": dict(per_dir_B),
            "composed_by": "apps/agent_dev/surface.py::build_dev_surface (default reader/writer)",
            "collateral_non_credential": len(collateral_B),
            "collateral_by_ext": dict(collections.Counter(pathlib.PurePosixPath(p).suffix or "<none>" for p, _ in collateral_B)),
            "collateral_by_pattern": dict(collections.Counter(pat for _, pats in collateral_B for pat in pats)),
        },
        "C_normalised_check": {
            "denied_total": len(denied_B) + len(denied_C_only),
            "normalisation_only_hits": len(denied_C_only),
            "note": "is_denied() runs raw fnmatch then NFKC/invisible/ADS/trailing/casefold canon; on an ASCII "
            "tracked tree canonical == raw so C == B unless a tracked name carries case/unicode variance",
        },
    },
    "B_minus_A": len(denied_B) - len(denied_A),
    "patterns_with_zero_tracked_hits_B": sorted(p for p in DENIED_PATH_PATTERNS if pattern_hits_B[p] == 0),
}

(OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
(OUT / "denied_A.txt").write_text("".join(p + "\n" for p in denied_A))
(OUT / "denied_B.txt").write_text("".join(p + "\n" for p in denied_B))
(OUT / "denied_C_only.txt").write_text("".join(p + "\n" for p in denied_C_only))
(OUT / "collateral_B.txt").write_text("".join(f"{p}\t{','.join(pats)}\n" for p, pats in collateral_B))

print(json.dumps({k: v for k, v in summary.items() if k != "patterns_with_zero_tracked_hits_B"}, indent=1))
print("zero-hit hardened patterns:", len(summary["patterns_with_zero_tracked_hits_B"]), "of", len(DENIED_PATH_PATTERNS))
