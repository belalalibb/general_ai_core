"""ProviderAgentModulePort behavioral semantics (T-IMPL-054; 30 §15.2–§15.4).

Hermetic — a fully in-memory fake implements the port and proves its
obligations without any network:

- runs are provider-managed opaque handles; lifecycle is the normalized
  12 §23.3 state set only.
- streamed events are the normalized 30 §15.3 shapes; a failed run's
  stream terminates with provider_agent.failed carrying a normalized error.
- provider-side tools stay denied unless the request explicitly grants
  them (30 §15.4 deny-by-default).
- cancellation moves the run to ``cancelled`` (30 §15.4 state cleanup).

Async methods are driven with asyncio.run (no pytest-asyncio; ADR-0001).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine
from typing import Any
from uuid import uuid4

from core.contracts.provider import ProviderError, ProviderErrorCategory
from core.contracts.provider_agent import (
    ProviderAgentEvent,
    ProviderAgentEventType,
    ProviderAgentRequest,
    ProviderAgentResponse,
    ProviderAgentRun,
    ProviderAgentRunState,
    ProviderAgentRunStatus,
)
from core.providers import ProviderAgentModulePort


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _request(**overrides: object) -> ProviderAgentRequest:
    payload: dict[str, object] = {
        "request_id": uuid4(),
        "tenant_id": uuid4(),
        "provider_agent_id": "fake_code_agent",
        "credential_ref": "cred-ref-opaque-1",
    }
    payload.update(overrides)
    return ProviderAgentRequest.model_validate(payload)


class FakeAgentModule:
    """In-memory ProviderAgentModulePort implementation (hermetic)."""

    def __init__(self) -> None:
        self._runs: dict[str, ProviderAgentRunStatus] = {}
        self._counter = 0
        self.tool_use_observed: list[bool] = []

    async def run_agent(self, request: ProviderAgentRequest) -> ProviderAgentResponse:
        self.tool_use_observed.append(request.provider_side_tools_allowed)
        return ProviderAgentResponse(
            request_id=request.request_id,
            succeeded=True,
            output={"text": "agent result"},
            usage={"tokens": 3},
        )

    async def create_agent_run(self, request: ProviderAgentRequest) -> ProviderAgentRun:
        self._counter += 1
        run_id = f"fake_thread/{self._counter}"  # provider-namespace handle
        self._runs[run_id] = ProviderAgentRunStatus(
            run_id=run_id, state=ProviderAgentRunState.RUNNING
        )
        return ProviderAgentRun(
            run_id=run_id,
            request_id=request.request_id,
            state=ProviderAgentRunState.PENDING,
        )

    async def get_agent_run(self, run_id: str) -> ProviderAgentRunStatus:
        return self._runs[run_id]

    async def cancel_agent_run(self, run_id: str) -> None:
        self._runs[run_id] = ProviderAgentRunStatus(
            run_id=run_id, state=ProviderAgentRunState.CANCELLED
        )

    def stream_agent_run(self, run_id: str) -> AsyncIterator[ProviderAgentEvent]:
        async def _events() -> AsyncIterator[ProviderAgentEvent]:
            yield ProviderAgentEvent(type=ProviderAgentEventType.STARTED, run_id=run_id)
            yield ProviderAgentEvent(
                type=ProviderAgentEventType.MESSAGE_DELTA,
                run_id=run_id,
                payload={"delta": "hello"},
            )
            status = self._runs[run_id]
            if status.state is ProviderAgentRunState.FAILED:
                assert status.error is not None
                yield ProviderAgentEvent(
                    type=ProviderAgentEventType.FAILED,
                    run_id=run_id,
                    error=status.error,
                )
            else:
                yield ProviderAgentEvent(type=ProviderAgentEventType.COMPLETED, run_id=run_id)

        return _events()

    def fail_run(self, run_id: str) -> None:
        self._runs[run_id] = ProviderAgentRunStatus(
            run_id=run_id,
            state=ProviderAgentRunState.FAILED,
            error=ProviderError(
                category=ProviderErrorCategory.RETRYABLE_SERVER_ERROR,
                retryable=True,
                safe_message="Provider agent run failed.",
            ),
        )


def _adapter() -> ProviderAgentModulePort:
    # The annotation itself proves FakeAgentModule satisfies the Protocol
    # structurally (mypy checks this assignment).
    adapter: ProviderAgentModulePort = FakeAgentModule()
    return adapter


def test_fake_satisfies_the_port_protocol() -> None:
    adapter = _adapter()
    assert isinstance(adapter, FakeAgentModule)


def test_one_shot_run_agent_returns_normalized_response() -> None:
    adapter = _adapter()
    response = run(adapter.run_agent(_request()))
    assert response.succeeded is True
    assert response.output == {"text": "agent result"}
    assert response.error is None


def test_provider_side_tools_denied_unless_explicitly_granted() -> None:
    fake = FakeAgentModule()
    run(fake.run_agent(_request()))
    run(fake.run_agent(_request(provider_side_tools_allowed=True)))
    assert fake.tool_use_observed == [False, True]


def test_run_lifecycle_uses_only_normalized_states() -> None:
    adapter = _adapter()
    handle = run(adapter.create_agent_run(_request()))
    assert handle.state is ProviderAgentRunState.PENDING
    status = run(adapter.get_agent_run(handle.run_id))
    assert status.state is ProviderAgentRunState.RUNNING
    run(adapter.cancel_agent_run(handle.run_id))
    cancelled = run(adapter.get_agent_run(handle.run_id))
    assert cancelled.state is ProviderAgentRunState.CANCELLED


def test_stream_emits_normalized_events_and_completes() -> None:
    adapter = _adapter()
    handle = run(adapter.create_agent_run(_request()))

    async def collect() -> list[ProviderAgentEvent]:
        return [event async for event in adapter.stream_agent_run(handle.run_id)]

    events = run(collect())
    assert [e.type for e in events] == [
        ProviderAgentEventType.STARTED,
        ProviderAgentEventType.MESSAGE_DELTA,
        ProviderAgentEventType.COMPLETED,
    ]


def test_failed_run_streams_failed_event_with_normalized_error() -> None:
    fake = FakeAgentModule()
    adapter: ProviderAgentModulePort = fake
    handle = run(adapter.create_agent_run(_request()))
    fake.fail_run(handle.run_id)

    async def collect() -> list[ProviderAgentEvent]:
        return [event async for event in adapter.stream_agent_run(handle.run_id)]

    events = run(collect())
    final = events[-1]
    assert final.type is ProviderAgentEventType.FAILED
    assert final.error is not None
    assert final.error.category is ProviderErrorCategory.RETRYABLE_SERVER_ERROR
    status = run(adapter.get_agent_run(handle.run_id))
    assert status.state is ProviderAgentRunState.FAILED
    assert status.error is not None
