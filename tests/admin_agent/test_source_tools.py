"""Agent source-inspection tools — mandate §9 (bounded engineering access).

Pins: absent seam = absent tools (P2); present seam = three R0 tools; the
jail/denylist refusals surface as typed DATA the model can adapt to (never
a crash); results are scrubbed like every other tool result; the tools are
read-only by class (R0) so the Tool Gate posture is unchanged.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from apps.admin_agent.dispatcher import ToolDispatcher
from apps.admin_agent.service import AdminAgentService
from apps.admin_agent.tools import build_registry
from core.tools.source_reader import SourceReader
from tests.admin_agent.test_aa2_admin_agent import AgentWorld, _reasoning


def run(coro: Any) -> Any:
    return asyncio.run(coro)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "engine.py").write_text("def route():\n    return 'decision'\n")
    (tmp_path / ".env").write_text("API_KEY=sk-abcdefghijklmnop1234\n")
    return tmp_path


def world_with_source(repo: Path, script: list[object] | None = None) -> AgentWorld:
    """AgentWorld whose surface carries a SourceReader (rebuilt seams)."""
    world = AgentWorld(script)
    world.surface = dataclasses.replace(world.surface, repo_reader=SourceReader(root=repo))
    world.registry = build_registry(world.surface)
    world.dispatcher = ToolDispatcher(world.registry, audit=world.audit)
    world.service = AdminAgentService(world.surface, world.registry, world.dispatcher)
    return world


class TestSeamOptionality:
    def test_absent_seam_means_absent_tools(self) -> None:
        world = AgentWorld()
        names = world.registry.names()
        assert "read_source_file" not in names
        assert "list_source_files" not in names
        assert "search_source" not in names

    def test_present_seam_registers_three_r0_tools(self, repo: Path) -> None:
        world = world_with_source(repo)
        described = {e["name"]: e["class"] for e in world.registry.describe()}
        assert described["read_source_file"] == "r0_read"
        assert described["list_source_files"] == "r0_read"
        assert described["search_source"] == "r0_read"


class TestDispatch:
    def test_read_file_returns_content(self, repo: Path) -> None:
        world = world_with_source(repo)
        record = run(
            world.dispatcher.dispatch(
                world.admin_principal(),
                "read_source_file",
                {"path": "core/engine.py"},
            )
        )
        assert record.ok is True
        assert record.result is not None
        assert "def route" in str(record.result["content"])

    def test_jail_refusal_is_typed_data_not_crash(self, repo: Path) -> None:
        world = world_with_source(repo)
        record = run(
            world.dispatcher.dispatch(
                world.admin_principal(),
                "read_source_file",
                {"path": "../outside.txt"},
            )
        )
        assert record.ok is True  # dispatch succeeded; the RESULT is a refusal
        assert record.result is not None
        assert record.result["error"] == "read refused"

    def test_denied_env_file_refused(self, repo: Path) -> None:
        world = world_with_source(repo)
        record = run(
            world.dispatcher.dispatch(world.admin_principal(), "read_source_file", {"path": ".env"})
        )
        assert record.ok is True
        assert record.result is not None
        assert record.result["error"] == "read refused"

    def test_search_and_list_work(self, repo: Path) -> None:
        world = world_with_source(repo)
        listing = run(world.dispatcher.dispatch(world.admin_principal(), "list_source_files", {}))
        assert listing.result is not None
        assert "core/engine.py" in listing.result["files"]
        found = run(
            world.dispatcher.dispatch(
                world.admin_principal(), "search_source", {"text": "def route"}
            )
        )
        assert found.result is not None
        assert found.result["matches"] != []

    def test_non_admin_refused(self, repo: Path) -> None:
        world = world_with_source(repo)
        record = run(
            world.dispatcher.dispatch(
                world.user_principal(), "read_source_file", {"path": "core/engine.py"}
            )
        )
        assert record.ok is False


class TestEndToEndScrubbing:
    def test_secretish_content_scrubbed_in_answer(self, repo: Path) -> None:
        # A NON-denied file that embeds a key-shaped string: content-level
        # scrubbing still protects the transcript.
        (repo / "core" / "config_sample.py").write_text('KEY = "sk-abcdefghijklmnop1234"\n')
        world = world_with_source(
            repo,
            [
                _reasoning(
                    tool_calls=[
                        {
                            "tool": "read_source_file",
                            "arguments": {"path": "core/config_sample.py"},
                        }
                    ]
                )
            ],
        )
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "read config"))
        blob = answer.model_dump_json()
        assert "sk-abcdefghijklmnop1234" not in blob
        assert "[SCRUBBED]" in blob

    def test_iterative_source_exploration(self, repo: Path) -> None:
        """Round 1 lists files; round 2 reads a file it SAW in round 1."""
        world = world_with_source(
            repo,
            [
                {
                    "content": json.dumps(
                        {
                            "tool_calls": [{"tool": "list_source_files", "arguments": {}}],
                            "claims": [],
                            "continue": True,
                        }
                    )
                },
                _reasoning(
                    tool_calls=[
                        {
                            "tool": "read_source_file",
                            "arguments": {"path": "core/engine.py"},
                        }
                    ]
                ),
            ],
        )
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "explore"))
        assert answer.rounds == 2
        assert answer.stop_reason == "final"
        by_tool = {c.tool: c for c in answer.tool_calls}
        assert by_tool["list_source_files"].ok
        assert by_tool["read_source_file"].ok
        # Round 2's ask carried round 1's listing (the observation loop).
        ask = str(world.adapter.requests[1].payload["ask"])
        assert "core/engine.py" in ask
