"""fixture_echo DEFINITION — deliberately COLLIDES with AssemblyAI's model name.

``qwen3.5-4b-32k-fast`` is the exact name AssemblyAI declares
(providers/assemblyai/definition.py). Same name, different slug, different
route token: if a request meant for one lands on the other, the answer
text (``FIXTURE_ECHO_MARKER``) says so at a glance. ``health_supported``
is False — nothing to probe.
"""

from __future__ import annotations

#: The one model name shared with a LIVE provider — the collision under test.
COLLIDING_MODEL_NAME = "qwen3.5-4b-32k-fast"

DEFINITION: dict[str, object] = {
    "display_name": "Fixture Echo (hermetic, routing-identity proof)",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {"chat": True},
    "operations": ["generate_text"],
    "models": [
        {"name": COLLIDING_MODEL_NAME, "context_window": 32768},
    ],
    "health_supported": False,
}
