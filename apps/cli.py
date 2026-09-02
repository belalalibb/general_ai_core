"""Unified run entrypoint — ``python3 -m apps.cli <command>``.

ONE door to the platform's EXISTING entrypoints (P3: compose, never
re-implement):

- ``serve``    → :func:`apps.main.main` (uvicorn factory; HOST/PORT env).
- ``check``    → ``engineering/verification/check_repo.sh`` (the repo gate:
                 governance files, pytest, mypy, ruff, import-linter, secret
                 scan) — exit code passes through verbatim.
- ``test``     → ``python3 -m pytest tests/`` (extra args forwarded).
- ``routes``   → enumerate the HTTP surface of the profile composed FROM THE
                 CURRENT ENVIRONMENT (``app.openapi()`` — the recorded
                 lazy-router posture) as JSON. Evidence, not a claim: what
                 is printed is what would be served.
- ``describe`` → profile facts as JSON (durable?, provider keys, demo
                 principal present?, agent catalog size, mounted UIs).

Nothing here owns behaviour; every command delegates to an existing
composition root or script so the CLI can never drift from the runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from starlette.routing import Mount

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK_REPO = REPO_ROOT / "engineering" / "verification" / "check_repo.sh"


def _serve(_: argparse.Namespace) -> int:
    from apps.main import main

    main()
    return 0


def _check(_: argparse.Namespace) -> int:
    if not CHECK_REPO.is_file():
        print(f"missing gate script: {CHECK_REPO}", file=sys.stderr)
        return 2
    return subprocess.call(["bash", str(CHECK_REPO)], cwd=REPO_ROOT)


def _test(args: argparse.Namespace) -> int:
    cmd = [sys.executable, "-m", "pytest", "tests/", *args.pytest_args]
    return subprocess.call(cmd, cwd=REPO_ROOT)


def _profile_facts() -> dict[str, object]:
    from apps.composition.runtime import build_runtime_profile

    profile = build_runtime_profile(environ=os.environ)
    paths = profile.app.openapi()["paths"]
    agent = profile.agent
    static_mounts = sorted(
        route.path
        for route in profile.app.routes
        if isinstance(route, Mount)  # StaticFiles mounts (/app, /admin)
    )
    return {
        "durable": profile.durable,
        "demo_principal": profile.demo_principal is not None,
        "provider_keys": list(profile.provider_keys),
        "agent_runtime": agent is not None,
        "agent_tools_offered": len(agent.surface.offered()) if agent is not None else 0,
        "route_count": len(paths),
        "ui_mounts": static_mounts,
        "routes": {
            path: sorted(m.upper() for m in methods) for path, methods in sorted(paths.items())
        },
    }


def _routes(_: argparse.Namespace) -> int:
    facts = _profile_facts()
    print(json.dumps(facts["routes"], indent=2, sort_keys=True))
    return 0


def _describe(_: argparse.Namespace) -> int:
    facts = _profile_facts()
    facts.pop("routes")
    print(json.dumps(facts, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m apps.cli",
        description="Unified entrypoint over the platform's existing composition roots.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve", help="run the platform (apps.main; HOST/PORT env)").set_defaults(
        run=_serve
    )
    sub.add_parser("check", help="run the repo gate (check_repo.sh)").set_defaults(run=_check)
    test = sub.add_parser("test", help="run the hermetic test suite (pytest args forwarded)")
    test.set_defaults(run=_test)
    sub.add_parser(
        "routes", help="print the HTTP surface of the env-composed profile"
    ).set_defaults(run=_routes)
    sub.add_parser("describe", help="print profile facts of the env-composed profile").set_defaults(
        run=_describe
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, extra = parser.parse_known_args(argv)
    if args.command == "test":
        args.pytest_args = extra  # every remaining token is pytest's
    elif extra:
        parser.error(f"unrecognized arguments: {' '.join(extra)}")
    result: int = args.run(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
