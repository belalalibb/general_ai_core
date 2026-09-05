#!/usr/bin/env python3
"""R173 F-15.2 — what the RUNTIME-composed source reader admits/refuses (before/after)."""

from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
from apps.composition.runtime import _source_reader  # noqa: E402

reader = _source_reader(os.getcwd())
assert reader is not None
probes = [
    ".env",
    ".git/config",
    "id_rsa.key",
    "../../etc/passwd",
    "core/agent/runtime.py",
    "engineering/verification/green_manifest.json",
    "engineering/verification/check_repo.sh",
    "core/providers/accounts.py",
    "infrastructure/security/password.py",
]
out = {}
for p in probes:
    try:
        reader.read_file(p)
        out[p] = "admitted"
    except Exception as e:  # noqa: BLE001
        out[p] = type(e).__name__
head = subprocess.run(
    ["git", "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True
).stdout.strip()
print(
    json.dumps(
        {"head": head, "reader_patterns": len(reader.denied_patterns), "probes": out},
        indent=1,
        sort_keys=True,
    )
)
