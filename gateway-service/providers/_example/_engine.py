"""Layer 1 — internal engine of the example provider. 100% FREE territory.

Demonstrates internal freedom: its own auth step, its own request shapes,
its own multi-step workflow — none of it visible outside the facade. A
real provider may replace all of this with an SDK, OAuth flows, session
cookies, account pools, N chained upstream calls, internal fallback —
anything, in any file layout.

example — not a live provider: the "upstream" is an in-process mock that
reacts to magic prompts so hermetic tests can drive every path without any
network.
"""

from __future__ import annotations

from providers._example._wire import MockUpstreamReply, MockUpstreamRequest

_VALID_KEY_PREFIX = "mock-key-"


def _mock_auth_check(api_key: str) -> str | None:
    """Internal auth step (Layer 1 freedom). Returns fail_code or None."""

    if not api_key.startswith(_VALID_KEY_PREFIX):
        return "401"
    return None


def call_mock_upstream(request: MockUpstreamRequest) -> MockUpstreamReply:
    """The pretend upstream. Magic prompts drive failure paths in tests:

    "TRIGGER_RATE_LIMIT" -> 429, "TRIGGER_SERVER_ERROR" -> 500,
    anything else -> success echo.
    """

    fail = _mock_auth_check(request.api_key)
    if fail is not None:
        return MockUpstreamReply(
            ok=False, body_text=None, tokens_in=0, tokens_out=0, fail_code=fail
        )
    if request.prompt_blob == "TRIGGER_RATE_LIMIT":
        return MockUpstreamReply(
            ok=False, body_text=None, tokens_in=0, tokens_out=0, fail_code="429"
        )
    if request.prompt_blob == "TRIGGER_SERVER_ERROR":
        return MockUpstreamReply(
            ok=False, body_text=None, tokens_in=0, tokens_out=0, fail_code="500"
        )
    reply_text = f"[mock:{request.model_id}] {request.prompt_blob}"
    return MockUpstreamReply(
        ok=True,
        body_text=reply_text,
        tokens_in=max(1, len(request.prompt_blob) // 4),
        tokens_out=max(1, len(reply_text) // 4),
        fail_code=None,
    )
