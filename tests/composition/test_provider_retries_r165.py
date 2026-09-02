"""R165 (live): ``PROVIDER_MAX_RETRIES`` — the bounded same-model retry budget.

Groq's free tier is 8k tokens/minute; a real multi-step agent brief costs
2-4k tokens per proposal, so the default single retry met the cap again
and the run died mid-task with ``rate_limited/rate_limit_exceeded``. The
operator can widen the budget; the run deadline still caps total wait.
"""

from __future__ import annotations

import pytest

from apps.composition.runtime import (
    DEFAULT_PROVIDER_RETRIES,
    MAX_PROVIDER_RETRIES,
    _provider_retries,
    build_runtime_profile,
)


def test_default_is_one_bounded_retry() -> None:
    assert _provider_retries({}) == DEFAULT_PROVIDER_RETRIES == 1
    assert _provider_retries({"PROVIDER_MAX_RETRIES": ""}) == 1


def test_operator_widens_or_disables_within_the_cap() -> None:
    assert _provider_retries({"PROVIDER_MAX_RETRIES": "4"}) == 4
    assert _provider_retries({"PROVIDER_MAX_RETRIES": "0"}) == 0
    assert _provider_retries({"PROVIDER_MAX_RETRIES": str(MAX_PROVIDER_RETRIES)}) == 8


@pytest.mark.parametrize("raw", ["-1", "9", "many", "1.5"])
def test_out_of_range_or_garbage_is_refused_at_boot(raw: str) -> None:
    with pytest.raises(ValueError, match="PROVIDER_MAX_RETRIES"):
        _provider_retries({"PROVIDER_MAX_RETRIES": raw})
    with pytest.raises(ValueError, match="PROVIDER_MAX_RETRIES"):
        build_runtime_profile(environ={"PROVIDER_MAX_RETRIES": raw})


def test_valid_value_boots() -> None:
    profile = build_runtime_profile(environ={"PROVIDER_MAX_RETRIES": "3"})
    assert profile.app is not None


def test_reasoning_budget_knob_reaches_the_runtime() -> None:
    """R165 (live): ``AGENT_REASONING_MAX_TOKENS`` is the per-call completion
    budget; out-of-range values fall back to the default like the other caps."""
    from core.agent import DEFAULT_REASONING_MAX_TOKENS

    tuned = build_runtime_profile(environ={"AGENT_REASONING_MAX_TOKENS": "2048"})
    assert tuned.agent is not None
    assert tuned.agent.surface.runtime._reasoning_max_tokens == 2048
    bad = build_runtime_profile(environ={"AGENT_REASONING_MAX_TOKENS": "999999"})
    assert bad.agent is not None
    assert bad.agent.surface.runtime._reasoning_max_tokens == DEFAULT_REASONING_MAX_TOKENS
