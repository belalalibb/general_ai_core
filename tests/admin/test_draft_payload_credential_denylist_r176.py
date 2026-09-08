"""R176 FIX-04 (F-R176-07): a config-change draft payload must never carry
credential material.

The contract docstring (core/contracts/admin.py, REGISTER_* actions) already
promises payloads carry "NEVER credential material (20 §5)" — but nothing
enforced it: a ``register_provider`` draft with ``api_key`` was stored (201)
and echoed on read-back (A6 L-14). This test fails on the parent commit and
passes once ``AdminDraftRequest`` refuses credential-shaped keys at any depth.

Opaque references (``credential_ref``, ``route_token_ref``) are the sanctioned
way to point at a secret and MUST stay admissible.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.contracts.admin import AdminAction, AdminDraftRequest

_DENIED_PAYLOADS: list[tuple[str, dict[str, object]]] = [
    ("top-level api_key", {"provider_key": "evil", "api_key": "sk-SHOULD-NOT-BE-STORED"}),
    ("apiKey camelCase", {"provider": {"apiKey": "x" * 20}}),
    ("nested secret", {"provider": {"auth": {"client_secret": "abc"}}}),
    ("password", {"account": {"password": "hunter2"}}),
    ("access_token", {"access_token": "eyJ.abc.def"}),
    ("private_key", {"tls": {"private_key": "-----BEGIN PRIVATE KEY-----"}}),
    ("token in list item", {"accounts": [{"name": "a"}, {"token": "t0k3n"}]}),
    ("credential (not _ref)", {"credential": {"value": "raw"}}),
]


@pytest.mark.parametrize("label,payload", _DENIED_PAYLOADS, ids=[p[0] for p in _DENIED_PAYLOADS])
def test_draft_refuses_credential_shaped_keys(label: str, payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError) as exc:
        AdminDraftRequest(action=AdminAction.REGISTER_PROVIDER, payload=payload)
    # Assert on the validator's own message — the part the API error envelope
    # renders (details.errors = [e["msg"]]). pydantic's full repr also prints
    # ``input_value=...`` for debugging; that never reaches the wire.
    msgs = [e["msg"] for e in exc.value.errors()]
    assert any("credential material" in m for m in msgs)
    joined = " ".join(msgs)
    # the offending VALUE must not be echoed by the validator's message
    assert "SHOULD-NOT-BE-STORED" not in joined and "hunter2" not in joined
    # and the offending KEY path is named (so the operator can find it)
    assert "payload" in joined


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_key": "groq", "credential_ref": "vault://groq/prod"},
        {"provider_key": "aai", "route_token_ref": "rt_aai_r174"},
        {"model_key": "local-echo-1"},
        {"plan": "pro", "task_units": 1000},
        {"provider": {"key": "groq", "display_name": "Groq", "auth_types": ["api_key"]}},
    ],
    ids=["credential_ref", "route_token_ref", "model_key", "plan", "auth_types-enum-value"],
)
def test_draft_admits_refs_and_ordinary_payloads(payload: dict[str, object]) -> None:
    req = AdminDraftRequest(action=AdminAction.REGISTER_PROVIDER, payload=payload)
    assert req.payload == payload
