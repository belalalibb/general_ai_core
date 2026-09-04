"""Handoff-review gap fixes — pinned hermetically.

Three gaps were proven LIVE against a real model during the Internal-Agent
self-sufficiency review (engineering/verification/INTERNAL_AGENT_SELF_SUFFICIENCY.md):

GAP-1a: ``_reason`` sent the admin message bare — a real model answers in
        prose, the parser (correctly) refuses it, and the loop is inert.
        Fix: the proposal protocol + registry.describe() now frame the ask.
GAP-1b: real models wrap JSON in ``` fences; the parser refused the fenced
        (otherwise valid) proposal. Fix: deterministic fence-stripping ONLY —
        no repair, no guessing.
GAP-2:  the in-memory profile granted the default budget ONLY to the demo
        principal; a registered admin's reasoning execution was refused
        (EntitlementNotConfigured). Fix: the SAME BudgetGrantingIdentity
        wrapper the durable branch already uses (symmetry, decision 5).

Honesty pins preserved: malformed output stays inert; invented evidence
stays refused (both pinned in test_aa2 — not repeated here).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from collections.abc import Coroutine
from typing import Any

from apps.admin_agent.service import AdminAgentService
from apps.composition.runtime import (
    DEFAULT_TASK_UNITS,
    DEV_DEMO_PRINCIPAL_ENV,
    BudgetGrantingIdentity,
    build_runtime_profile,
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


# --- GAP-1a: protocol framing --------------------------------------------------------


class TestProtocolFraming:
    def test_reason_ask_carries_protocol_tools_and_message(self) -> None:
        """The ask the model sees = protocol + registry.describe() + message.

        Pinned via source (the framing is deterministic string composition;
        executing it needs a full world — test_aa2 covers the loop)."""
        import inspect

        from apps.admin_agent import service as svc

        assert "_PROPOSAL_PROTOCOL" in dir(svc)
        protocol = svc._PROPOSAL_PROTOCOL  # noqa: SLF001 — pinned constant
        # The contract the parser enforces, stated to the model verbatim:
        assert '"tool_calls"' in protocol
        assert '"claims"' in protocol
        assert "evidence" in protocol
        assert "{tools}" in protocol and "{message}" in protocol
        source = inspect.getsource(svc.AdminAgentService._reason)
        assert "_PROPOSAL_PROTOCOL" in source
        assert "describe()" in source


# --- GAP-1b: fence stripping (deterministic, no repair) ------------------------------


class TestFenceStripping:
    def _parse(self, raw: str) -> tuple[object, str | None]:
        return AdminAgentService._parse_proposals(raw)  # noqa: SLF001

    def test_fenced_json_proposal_parses(self) -> None:
        inner = json.dumps({"tool_calls": [], "claims": []})
        parsed, note = self._parse(f"```json\n{inner}\n```")
        assert note is None
        assert parsed == {"tool_calls": [], "claims": []}

    def test_bare_fence_variant_parses(self) -> None:
        inner = json.dumps({"tool_calls": [], "claims": []})
        parsed, note = self._parse(f"```\n{inner}\n```")
        assert note is None
        assert parsed is not None

    def test_prose_still_refused(self) -> None:
        parsed, note = self._parse("I will now run a test execution for you.")
        assert parsed is None
        assert note == "model output was not a valid proposal; nothing dispatched"

    def test_fenced_garbage_still_refused(self) -> None:
        parsed, note = self._parse("```json\nnot json at all\n```")
        assert parsed is None
        assert note is not None

    def test_unfenced_json_unchanged(self) -> None:
        parsed, note = self._parse('{"tool_calls": [], "claims": []}')
        assert note is None
        assert parsed == {"tool_calls": [], "claims": []}


# --- GAP-2: in-memory profile budget symmetry ----------------------------------------


class TestInMemoryBudgetGrant:
    def test_registered_user_gets_default_budget(self) -> None:
        """register → verify → login in the in-memory profile grants the
        composition-data default budget (same wrapper as durable)."""
        prof = build_runtime_profile(environ={})
        assert isinstance(prof.identity, BudgetGrantingIdentity)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            user = prof.identity.register("gap2@example.com", "correct horse battery staple", "en")
        token = json.loads(stream.getvalue())["token"]
        prof.identity.verify_email(token)
        prof.identity.login("gap2@example.com", "correct horse battery staple")
        summary = prof.usage.summary(user.tenant_id)
        assert summary.task_units.limit == DEFAULT_TASK_UNITS

    def test_demo_principal_budget_unchanged(self) -> None:
        """The demo principal's explicit grant is untouched by the wrapper."""
        prof = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})  # R168 D-07 opt-in
        assert prof.demo_principal is not None
        summary = prof.usage.summary(prof.demo_principal.tenant_id)
        assert summary.task_units.limit == DEFAULT_TASK_UNITS
