"""Unified entrypoint (R160) — ``python3 -m apps.cli`` composes, never re-implements.

Pins: every command delegates to an EXISTING root (apps.main / check_repo.sh
/ pytest / build_runtime_profile); ``routes``/``describe`` print evidence
from the actually composed profile (the same openapi() enumeration the
console tests use); unknown command exits non-zero via argparse.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from apps import cli

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestDelegation:
    def test_serve_delegates_to_apps_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        import apps.main

        monkeypatch.setattr(apps.main, "main", lambda: called.append("served"))
        assert cli.main(["serve"]) == 0
        assert called == ["served"]

    def test_check_runs_the_repo_gate_script(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []
        monkeypatch.setattr(cli.subprocess, "call", lambda cmd, cwd: seen.append(cmd) or 7)
        assert cli.main(["check"]) == 7  # exit code passes through verbatim
        assert seen[0][0] == "bash" and seen[0][1].endswith("check_repo.sh")
        assert cli.CHECK_REPO.is_file()

    def test_test_forwards_pytest_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[list[str]] = []
        monkeypatch.setattr(cli.subprocess, "call", lambda cmd, cwd: seen.append(cmd) or 0)
        assert cli.main(["test", "-k", "nothing", "-q"]) == 0
        assert seen[0][:3] == [sys.executable, "-m", "pytest"]
        assert seen[0][3] == "tests/" and seen[0][4:] == ["-k", "nothing", "-q"]


class TestEvidence:
    def test_routes_prints_the_composed_surface(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("DATABASE_URL", "GROQ_API_KEY", "GSK_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        assert cli.main(["routes"]) == 0
        routes = json.loads(capsys.readouterr().out)
        # The generic surfaces AND the composed admin surfaces are all there.
        for path in ("/v1/execute", "/v1/agent-tools", "/v1/skills", "/v1/admin/skills/import"):
            assert path in routes, path
        assert routes["/v1/execute"] == ["POST"]

    def test_describe_reports_profile_facts(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("DATABASE_URL", "GROQ_API_KEY", "GSK_API_KEY", "DEV_DEMO_PRINCIPAL"):
            monkeypatch.delenv(var, raising=False)
        assert cli.main(["describe"]) == 0
        facts = json.loads(capsys.readouterr().out)
        assert facts["durable"] is False
        # R168 D-07: the header-less demo principal is closed by default.
        assert facts["demo_principal"] is False
        assert facts["agent_runtime"] is True
        assert "/app" in facts["ui_mounts"] and "/admin" in facts["ui_mounts"]
        assert facts["route_count"] > 50
        assert "routes" not in facts

    def test_describe_reports_dev_opt_in_demo_principal(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for var in ("DATABASE_URL", "GROQ_API_KEY", "GSK_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("DEV_DEMO_PRINCIPAL", "1")
        assert cli.main(["describe"]) == 0
        facts = json.loads(capsys.readouterr().out)
        assert facts["demo_principal"] is True

    def test_unknown_command_is_refused(self) -> None:
        with pytest.raises(SystemExit) as exc:
            cli.main(["dance"])
        assert exc.value.code != 0

    def test_module_is_runnable(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "apps.cli", "--help"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        for cmd in ("serve", "check", "test", "routes", "describe"):
            assert cmd in proc.stdout
