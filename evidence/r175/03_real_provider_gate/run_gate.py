"""R175 §3 — REAL-PROVIDER HARD GATE driver (secret-safe, raw -> evidence promotion).

Rule (set by the operator for R175): the seven Groq-gated tests are RAW
material, not evidence, until a REAL upstream call to api.groq.com has
succeeded in this very run. Concretely:

  * The driver runs the three live modules with the key in the environment.
  * pytest's own `-rA` report is the primary artifact. Promotion to
    `evidence/` requires EXACTLY: 7 passed, 0 skipped, 0 failed, 0 errors.
  * Anything else (skips because the key was absent, an upstream 4xx/5xx,
    a network failure) lands in `raw/` and is marked NOT_PROMOTED — it is
    kept for honesty but carries no certification weight.
  * A separate independent upstream probe (one GET /openai/v1/models, free)
    is recorded BEFORE pytest so a failure can be attributed: key/upstream
    problem vs. platform problem.

Key custody:
  * Ingress is environment-only: GROQ_API_KEY (platform adapter tests) and
    GW_GROQ_API_KEY (gateway Layer-1 resolution). They MAY differ (one key
    per surface); each distinct key is probed independently and promotion
    requires every probe to be OK. The driver never reads a file inside the
    repository and never receives a key as an argument.
  * Every artifact is passed through `_scrub` (every literal key + `gsk_`
    shape) and asserted free of all of them before it is written.
  * The key is NOT forwarded to the subprocess environment beyond the two
    named variables; PYTHONWARNINGS etc. are inherited normally.

Run:   GROQ_API_KEY=<k> GW_GROQ_API_KEY=<k> python3 evidence/r175/03_real_provider_gate/run_gate.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
RAW = OUT / "raw"
KEY_ENVS = ("GROQ_API_KEY", "GW_GROQ_API_KEY")
MODULES = (
    "tests/providers/test_groq_live.py",
    "tests/providers/test_groq_live_e2e.py",
    "tests/providers/test_gateway_groq_live_e2e.py",
)
EXPECTED_PASSED = 7
KEY_SHAPE = re.compile(r"gsk_[A-Za-z0-9]{20,}")


def _keys() -> dict[str, str]:
    """env-name -> key for every populated KEY_ENV (empty dict = no key)."""
    found = {e: os.environ.get(e, "") for e in KEY_ENVS}
    found = {e: v for e, v in found.items() if v}
    if found and len(found) != len(KEY_ENVS):
        sys.exit(f"partial key set: {sorted(found)} — both {KEY_ENVS} are required")
    return found


def _scrub(text: str, keys: dict[str, str]) -> str:
    for env, key in keys.items():
        text = text.replace(key, f"<redacted:{env}>")
    text = KEY_SHAPE.sub("<redacted-gsk-shape>", text)
    return text


def _write(path: Path, text: str, keys: dict[str, str]) -> None:
    text = _scrub(text, keys)
    assert all(k not in text for k in keys.values()), "literal key survived scrub"
    assert not KEY_SHAPE.search(text), "gsk_ shape survived scrub"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n")


def upstream_probe(key: str | None) -> dict:
    """Independent, free, attribution probe: GET /openai/v1/models."""
    if key is None:
        return {"status": "SKIPPED", "reason": "no key in env"}
    t0 = time.monotonic()
    try:
        r = httpx.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=20,
        )
    except httpx.HTTPError as exc:  # network / TLS / timeout
        return {"status": "ERROR", "error": type(exc).__name__, "detail": str(exc)}
    ms = round((time.monotonic() - t0) * 1000)
    body: dict = {}
    try:
        body = r.json()
    except ValueError:
        pass
    ids = sorted(m.get("id", "") for m in body.get("data", [])) if r.status_code == 200 else []
    return {
        "status": "OK" if r.status_code == 200 else "HTTP_" + str(r.status_code),
        "http_status": r.status_code,
        "latency_ms": ms,
        "model_count": len(ids),
        "allam-2-7b_present": "allam-2-7b" in ids,
        "error": body.get("error") if r.status_code != 200 else None,
    }


def run_pytest(keys: dict[str, str]) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k not in KEY_ENVS}
    env.update(keys)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *MODULES,
        "-q",
        "-rA",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=",
        "-W",
        "ignore::DeprecationWarning",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    stderr = "\n--- stderr ---\n" + proc.stderr if proc.stderr.strip() else ""
    return proc.returncode, proc.stdout + stderr


def parse_summary(report: str) -> dict:
    tail = report.strip().splitlines()[-1] if report.strip() else ""
    counts = {k: 0 for k in ("passed", "failed", "skipped", "error", "errors", "xfailed")}
    for n, k in re.findall(r"(\d+) (passed|failed|skipped|errors?|xfailed)", tail):
        counts[k] = int(n)
    counts["error"] = counts["error"] + counts.pop("errors")
    return {"summary_line": tail, **counts}


def main() -> int:
    keys = _keys()
    started = datetime.now(UTC).isoformat(timespec="seconds")
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()

    # one probe per DISTINCT key, reported under every env name that carries it
    probe_by_key = {k: upstream_probe(k) for k in set(keys.values())}
    probe = (
        {env: probe_by_key[k] for env, k in keys.items()}
        if keys
        else {"status": "SKIPPED", "reason": "no key in env"}
    )
    probes_ok = bool(keys) and all(p.get("status") == "OK" for p in probe_by_key.values())
    rc, report = run_pytest(keys)
    summary = parse_summary(report)

    promoted = (
        probes_ok
        and rc == 0
        and summary["passed"] == EXPECTED_PASSED
        and summary["skipped"] == 0
        and summary["failed"] == 0
        and summary["error"] == 0
    )
    dest = OUT if promoted else RAW
    verdict = {
        "run_started_utc": started,
        "head": head,
        "key_present_in_env": bool(keys),
        "key_env_names": list(KEY_ENVS),
        "distinct_keys": len(set(keys.values())),
        "upstream_probe": probe,
        "pytest_exit": rc,
        "pytest_summary": summary,
        "expected": {"passed": EXPECTED_PASSED, "skipped": 0, "failed": 0, "error": 0},
        "PROMOTED": promoted,
        "disposition": (
            "EVIDENCE — real upstream call succeeded through every live module; the 7 tests count"
            if promoted
            else "NOT_PROMOTED — raw only; the 7 Groq tests carry no certification "
            "weight for this run"
        ),
        "paid_calls_upper_bound": (
            # test_groq_live: 1 generation; groq_live_e2e: 1 execute; gateway e2e: 2 entry points
            4 if promoted else "unknown (see report)"
        ),
    }
    _write(dest / "pytest_live_report.txt", report, keys)
    _write(dest / "verdict.json", json.dumps(verdict, indent=2), keys)
    shown = ("PROMOTED", "pytest_summary", "upstream_probe", "disposition")
    print(json.dumps({k: verdict[k] for k in shown}, indent=2))
    return 0 if promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
