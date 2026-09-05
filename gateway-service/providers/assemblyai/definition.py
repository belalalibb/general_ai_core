"""AssemblyAI DEFINITION — the provider's official declaration (deny-by-default).

The registry trusts ONLY this declaration — never code introspection.
R174 scope: ``generate_text`` ONLY; models limited to what the live E2E
actually exercises (Groq precedent: declare what you exercise).
``health_supported`` is False — AssemblyAI's LLM gateway documents no
``/models`` or health endpoint and no probe is implemented, so the honest
answer is UNKNOWN (never guessed OK).

Context windows are taken from AssemblyAI's published model table
(evidence/r174/01_read/assemblyai_available_models.md, fetched 2026-09-05).
"""

from __future__ import annotations

DEFINITION: dict[str, object] = {
    "display_name": "AssemblyAI LLM Gateway",
    "definition_version": "1.0.0",
    "credential_mode": "platform",
    "capabilities": {"chat": True, "reasoning": True, "code": True},
    "operations": ["generate_text"],
    "models": [
        {"name": "qwen3.5-4b-32k-fast", "context_window": 32768},
        {"name": "gemini-2.5-flash-lite", "context_window": 1048576},
    ],
    "health_supported": False,
}
