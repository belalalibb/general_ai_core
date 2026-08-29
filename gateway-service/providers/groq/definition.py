"""Groq DEFINITION — the provider's official declaration (deny-by-default).

The registry trusts ONLY this declaration — never code introspection.
G3 scope: ``generate_text`` ONLY; models limited to what the live E2E
actually exercises. ``health_supported`` is False — no upstream health
probe is implemented, so the honest answer is UNKNOWN (never guessed OK).
"""

from __future__ import annotations

DEFINITION: dict[str, object] = {
    "display_name": "Groq",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {"chat": True, "reasoning": True, "code": True},
    "operations": ["generate_text"],
    "models": [
        {"name": "allam-2-7b", "context_window": 4096},
        {"name": "llama-3.1-8b-instant", "context_window": 131072},
    ],
    "health_supported": False,
}
