"""DEFINITION template — the provider's official declaration. FILL ME IN.

RULES (deny-by-default — the registry trusts ONLY this declaration):

- Declare ONLY what actually works. An undeclared operation simply does
  not exist for this provider (requests get `unsupported_capability`).
- Every declared operation MUST have a handler in adapter.py HANDLERS,
  and every handler MUST be declared here — mismatch = STARTUP failure.
- Do NOT declare run_provider_agent / upload_asset / download_asset:
  they are excluded from Gateway v1 (ADR-0008 OPEN-2) and any DEFINITION
  declaring them is REJECTED AT LOAD TIME.
- An unsupported operation is NOT represented by an empty declared stub —
  declaration IS the source of eligibility; leave it out entirely.
- capabilities keys come from the platform's CLOSED set (see
  gateway.contracts.CAPABILITY_KEYS); unknown keys are rejected.
- models: [] is honest and valid if you declare none.
- definition_version: semver X.Y.Z; bump it on any declaration change —
  the platform rebuilds its manifest from it, nothing else.
"""

from __future__ import annotations

DEFINITION: dict[str, object] = {
    # The ONLY name that crosses the boundary (5-layer identity model).
    "display_name": "FILL_ME Human-Readable Provider Name",
    # Semver. Bump on every declaration change.
    "definition_version": "0.1.0",
    # "user_key" (platform sends the user's key in the envelope, memory-only
    # here) OR "platform" (YOU resolve credentials internally, keyed by your
    # own means — the platform never learns the kind).
    "credential_mode": "user_key",
    # Deny-by-default over the platform's closed capability keys.
    # Only list keys you set to True; everything else is False.
    "capabilities": {
        # "chat": True,
    },
    # ONLY operations with a working handler in adapter.py. Subset of the
    # 8 v1 operations (see adapter.py for each one's contract).
    "operations": [
        # "generate_text",
    ],
    # Declared models; [] is valid.
    "models": [
        # {"name": "upstream-model-name", "context_window": 128000},
    ],
    # False => /v1/health answers UNKNOWN (honest).
    "health_supported": False,
}
