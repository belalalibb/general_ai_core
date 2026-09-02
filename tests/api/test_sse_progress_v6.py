"""SSE progress endpoint — Vision V6 chunk 2 gates (10 §11 events).

Two layers:

1. Pure derivation (derive_events / sse_frame): report → the closed
   10 §11 event vocabulary; deterministic; terminal tail only when the
   execution is terminal; frames are valid SSE data lines.
2. HTTP surface over the real app (httpx ASGI transport, World harness):
   seam OFF ⇒ route absent (404 for everything, 20 §4); seam ON ⇒
   terminal executions stream their full derived sequence and close;
   in-flight executions stream incrementally as the store progresses;
   timeout closes with a named error event; unknown/foreign ids are the
   plain 404 BEFORE any stream; stream=true on POST /v1/execute KEEPS
   its recorded loud rejection (this endpoint is progress, not inline
   result streaming — fabricating deltas would violate 41 §49).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any
from uuid import uuid4

import httpx
from fastapi import FastAPI

from apps.api import create_app
from apps.api.streaming import derive_events, sse_frame
from core.contracts.base import utc_now
from core.contracts.execute import ExecutionStatus
from core.contracts.execution import (
    Execution,
    ExecutionNode,
    ExecutionNodeStatus,
    ExecutionNodeType,
    ExecutionStrategy,
)
from core.execution.service import ExecutionReport, ExecutionService, NodeReport
from core.routing.router import SimpleScoringRouter
from tests.api.test_execute_api import World


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(seconds: float) -> None:
    return None


def _report(
    world: World,
    *,
    status: ExecutionStatus,
    node_states: list[ExecutionNodeStatus] | None = None,
) -> ExecutionReport:
    execution_id = uuid4()
    nodes = tuple(
        NodeReport(
            node=ExecutionNode(
                id=uuid4(),
                execution_id=execution_id,
                node_key=f"stage-{index}",
                type=ExecutionNodeType.MODEL_CALL,
                status=state,
                input_ref={},
                retry_count=0,
            ),
            attempts=(),
            response=None,
        )
        for index, state in enumerate(node_states or [])
    )
    return ExecutionReport(
        execution=Execution(
            id=execution_id,
            tenant_id=world.principal.tenant_id,
            user_id=world.principal.user_id,
            request_hash="sha256:x",
            status=status,
            strategy=ExecutionStrategy.SINGLE,
            cost_snapshot={},
            created_at=utc_now(),
        ),
        nodes=nodes,
        status_history=(status,),
    )


def _sse_app(world: World, *, timeout: float = 60.0) -> FastAPI:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        sse=True,
        sse_poll_interval_seconds=0.01,
        sse_timeout_seconds=timeout,
        sse_sleeper=_no_sleep,
    )


async def _stream(app: FastAPI, path: str) -> tuple[int, str, list[dict[str, Any]]]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get(path)
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        return (
            response.status_code,
            response.headers.get("content-type", ""),
            events,
        )


class TestDerivation:
    def test_succeeded_report_derives_full_sequence(self) -> None:
        world = World()
        report = _report(
            world,
            status=ExecutionStatus.SUCCEEDED,
            node_states=[ExecutionNodeStatus.SUCCEEDED],
        )
        types = [event.type for event in derive_events(report)]
        assert types == [
            "execution_started",
            "node_started",
            "node_completed",
            "final",
        ]

    def test_failed_report_ends_with_error(self) -> None:
        world = World()
        report = _report(
            world,
            status=ExecutionStatus.FAILED,
            node_states=[ExecutionNodeStatus.FAILED],
        )
        events = derive_events(report)
        assert events[-1].type == "error"

    def test_running_report_has_no_terminal_tail(self) -> None:
        world = World()
        report = _report(
            world,
            status=ExecutionStatus.RUNNING,
            node_states=[ExecutionNodeStatus.RUNNING],
        )
        types = [event.type for event in derive_events(report)]
        # A RUNNING node contributes only its started half; no final/error.
        assert types == ["execution_started", "node_started"]

    def test_queued_report_is_started_only(self) -> None:
        world = World()
        report = _report(world, status=ExecutionStatus.QUEUED)
        types = [event.type for event in derive_events(report)]
        assert types == ["execution_started"]

    def test_derivation_is_deterministic(self) -> None:
        world = World()
        report = _report(
            world,
            status=ExecutionStatus.SUCCEEDED,
            node_states=[ExecutionNodeStatus.SUCCEEDED],
        )
        assert derive_events(report) == derive_events(report)

    def test_sse_frame_shape(self) -> None:
        world = World()
        report = _report(world, status=ExecutionStatus.QUEUED)
        frame = sse_frame(derive_events(report)[0])
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        payload = json.loads(frame.removeprefix("data: ").strip())
        assert payload["type"] == "execution_started"
        assert payload["execution_id"] == str(report.execution.id)


class TestHttpSurface:
    def test_seam_absent_route_does_not_exist(self) -> None:
        world = World()
        app = world.app()  # sse not passed — default off
        status, _, _ = run(_stream(app, f"/v1/executions/{uuid4()}/events"))
        assert status == 404  # route absent entirely (20 §4)
        ops = [
            f"{method.upper()} {path}"
            for path, methods in (app.openapi().get("paths") or {}).items()
            for method in methods
        ]
        assert not any("/events" in op for op in ops)

    def test_terminal_execution_streams_full_sequence_and_closes(self) -> None:
        world = World()
        report = _report(
            world,
            status=ExecutionStatus.SUCCEEDED,
            node_states=[ExecutionNodeStatus.SUCCEEDED],
        )
        world.store.put(report)
        app = _sse_app(world)
        status, content_type, events = run(
            _stream(app, f"/v1/executions/{report.execution.id}/events")
        )
        assert status == 200
        assert content_type.startswith("text/event-stream")
        assert [event["type"] for event in events] == [
            "execution_started",
            "node_started",
            "node_completed",
            "final",
        ]

    def test_in_flight_execution_streams_incrementally(self) -> None:
        """The store progresses while the stream polls — events arrive
        incrementally and the stream closes on the terminal report."""
        world = World()
        queued = _report(world, status=ExecutionStatus.QUEUED)
        world.store.put(queued)
        execution_id = queued.execution.id

        # After the first poll, a "worker" swaps in the terminal report
        # (same id, same tenant — exactly what the V2 worker does).
        polls = 0
        original_get = world.store.get

        def progressing_get(tenant_id: Any, eid: Any) -> ExecutionReport:
            nonlocal polls
            polls += 1
            if polls > 1:
                import dataclasses

                terminal = _report(
                    world,
                    status=ExecutionStatus.SUCCEEDED,
                    node_states=[ExecutionNodeStatus.SUCCEEDED],
                )
                # ExecutionReport is a dataclass; Execution a Pydantic model.
                terminal = dataclasses.replace(
                    terminal,
                    execution=terminal.execution.model_copy(update={"id": execution_id}),
                )
                return terminal
            return original_get(tenant_id, eid)

        world.store.get = progressing_get  # type: ignore[method-assign]
        app = _sse_app(world)
        status, _, events = run(_stream(app, f"/v1/executions/{execution_id}/events"))
        assert status == 200
        types = [event["type"] for event in events]
        assert types[0] == "execution_started"
        assert types[-1] == "final"
        assert "node_completed" in types

    def test_timeout_closes_with_named_error_event(self) -> None:
        world = World()
        queued = _report(world, status=ExecutionStatus.QUEUED)
        world.store.put(queued)
        app = _sse_app(world, timeout=0.02)  # poll 0.01 — expires fast
        status, _, events = run(_stream(app, f"/v1/executions/{queued.execution.id}/events"))
        assert status == 200
        assert events[-1]["type"] == "error"
        assert events[-1]["error"]["reason"] == "stream_timeout"

    def test_unknown_id_is_plain_404_never_a_stream(self) -> None:
        world = World()
        app = _sse_app(world)
        status, content_type, _ = run(_stream(app, f"/v1/executions/{uuid4()}/events"))
        assert status == 404
        assert content_type.startswith("application/json")

    def test_foreign_tenant_indistinguishable_from_absent(self) -> None:
        owner = World()
        report = _report(owner, status=ExecutionStatus.SUCCEEDED)
        # Store the report under ANOTHER world's store? No — same store,
        # different principal: build an app whose caller is a stranger.
        stranger = World()
        stranger.store = owner.store  # shared store, foreign principal
        owner.store.put(report)
        app = _sse_app(stranger)
        status, _, _ = run(_stream(app, f"/v1/executions/{report.execution.id}/events"))
        assert status == 404  # byte-identical to absent (20 §6)

    def test_malformed_id_is_422(self) -> None:
        world = World()
        app = _sse_app(world)
        status, _, _ = run(_stream(app, "/v1/executions/not-a-uuid/events"))
        assert status == 422

    def test_execute_stream_true_keeps_loud_rejection(self) -> None:
        """SSE progress is NOT inline result streaming — the recorded
        POST /v1/execute rejection stands (fabricated deltas = 41 §49)."""

        async def post() -> httpx.Response:
            world = World()
            app = _sse_app(world)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
                return await client.post(
                    "/v1/execute",
                    json={"ask": "hi", "execution_policy": {"stream": True}},
                )

        response = run(post())
        assert response.status_code == 422
        assert "Streaming is not available" in response.text
