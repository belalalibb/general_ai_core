"""R4-forbidden content scrubbing — AA-2 acceptance criterion 4.

Extends the G4 leak-test posture: classes of strings that must NEVER reach
an agent transcript, claim, or UI payload are pattern-scrubbed from every
tool result and every admitted claim. Patterns cover:

- opaque credential handles (``secret-ref://``, ``credential_ref=``),
- provider API key shapes (``sk-``, ``gsk_``, ``AKIA``, ``gwsecret_``),
- bearer/JWT material (``Bearer <token>``, ``eyJ...``),
- PEM private-key blocks,
- URLs (gateway secrecy — upstream endpoints are never surfaced).

Scrubbing is deliberately loud (``[SCRUBBED]``), never silent deletion:
the transcript shows WHERE something was withheld.
"""

from __future__ import annotations

import re
from typing import Any

from core.contracts.base import JsonObject

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"secret-ref://\S+"),
    re.compile(r"credential_ref=\S+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{4,}\.?[A-Za-z0-9_-]*"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgwsecret_[A-Za-z0-9_-]{4,}"),
    re.compile(r"https?://\S+"),
]

_REPLACEMENT = "[SCRUBBED]"


def scrub_text(text: str) -> str:
    """Replace every R4-forbidden match in ``text`` with ``[SCRUBBED]``."""
    for pattern in _PATTERNS:
        text = pattern.sub(_REPLACEMENT, text)
    return text


def scrub_json(value: Any) -> Any:  # noqa: ANN401 - recursive JSON walker
    """Recursively scrub strings inside any JSON-like structure."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {key: scrub_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub_json(item) for item in value]
    return value


def scrub_object(payload: JsonObject) -> JsonObject:
    """Typed wrapper: dict in, dict out (mypy-strict seam over scrub_json)."""
    scrubbed = scrub_json(payload)
    assert isinstance(scrubbed, dict)
    return scrubbed
