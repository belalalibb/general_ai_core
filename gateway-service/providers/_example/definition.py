"""EXAMPLE DEFINITION — the provider's official declaration (deny-by-default).

The registry trusts ONLY this declaration — never code introspection.
Declare only what actually works; every declared operation MUST have a
facade handler (startup parity check) and vice versa.

example — not a live provider.
"""

from __future__ import annotations

DEFINITION: dict[str, object] = {
    "display_name": "Example Provider (mock)",
    "definition_version": "1.0.0",
    "credential_mode": "user_key",
    "capabilities": {"chat": True},
    "operations": ["generate_text"],
    "models": [{"name": "example-mock-model", "context_window": 8192}],
    "health_supported": False,
}
