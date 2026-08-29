"""Layer 1 helper — internal wire shapes for the MOCK upstream.

This file exists to demonstrate that Layer 1 may be split across any number
of internal modules with any internal shapes. NOTHING here is visible to
the gateway or the platform; only adapter.py (the facade) crosses.

example — not a live provider. There is NO real upstream: the "upstream"
is an in-process mock.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MockUpstreamRequest:
    """The mock upstream's OWN request shape — deliberately different from
    the canonical contract, to prove the facade must translate."""

    api_key: str
    model_id: str
    prompt_blob: str
    max_units: int


@dataclass(frozen=True)
class MockUpstreamReply:
    """The mock upstream's OWN reply shape (weird on purpose)."""

    ok: bool
    body_text: str | None
    tokens_in: int
    tokens_out: int
    fail_code: str | None  # e.g. "429", "401", "500" — upstream-native codes
