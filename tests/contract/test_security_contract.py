"""Contract tests: security contract (20 §4 Capability Firewall).

Verifies the decision output set matches 20 §4 verbatim, the documented
decision-input example validates field-for-field, approval_state is closed
to approved|null, the LLM is not an actor kind, unknown fields/values are
rejected (deny-by-default), and instances are frozen value objects with
closed JSON Schema exports.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.security import (
    ActorKind,
    FirewallDecision,
    FirewallDecisionInput,
)

# --- Closed sets exactly as written in 20 §4 ------------------------------------


def test_firewall_decision_set_matches_spec() -> None:
    # 20 §4 output: ALLOW / DENY / ALLOW_WITH_LIMIT / REQUIRE_APPROVAL
    assert {d.value for d in FirewallDecision} == {
        "ALLOW",
        "DENY",
        "ALLOW_WITH_LIMIT",
        "REQUIRE_APPROVAL",
    }


def test_actor_kind_set_matches_spec() -> None:
    # 20 §4: actor = "user_or_system" → user|system; the LLM is never an
    # authority actor (20 §1).
    assert {a.value for a in ActorKind} == {"user", "system"}
    assert "llm" not in {a.value for a in ActorKind}
    assert "model" not in {a.value for a in ActorKind}


# --- Documented example validates (20 §4, field-for-field) ----------------------


def _decision_input_payload(**overrides: Any) -> dict[str, Any]:
    # Mirrors the 20 §4 JSON example exactly (actor kind resolved to "user";
    # tenant_id example value "uuid" carried as a real UUID).
    payload: dict[str, Any] = {
        "actor": "user",
        "tenant_id": str(uuid4()),
        "permission": "github.pr.create",
        "resource": "repo:owner/name",
        "scope": "project",
        "entitlement": "github_write",
        "approval_state": "approved",
        "risk_level": "medium",
    }
    payload.update(overrides)
    return payload


def test_documented_decision_input_example_validates() -> None:
    decision_input = FirewallDecisionInput.model_validate(_decision_input_payload())
    assert decision_input.actor is ActorKind.USER
    assert decision_input.permission == "github.pr.create"
    assert decision_input.resource == "repo:owner/name"
    assert decision_input.scope == "project"
    assert decision_input.entitlement == "github_write"
    assert decision_input.approval_state == "approved"
    assert decision_input.risk_level == "medium"


def test_approval_state_accepts_null() -> None:
    # 20 §4: approval_state: "approved|null"
    decision_input = FirewallDecisionInput.model_validate(
        _decision_input_payload(approval_state=None)
    )
    assert decision_input.approval_state is None


def test_approval_state_defaults_to_null() -> None:
    payload = _decision_input_payload()
    del payload["approval_state"]
    assert FirewallDecisionInput.model_validate(payload).approval_state is None


def test_system_actor_accepted() -> None:
    decision_input = FirewallDecisionInput.model_validate(_decision_input_payload(actor="system"))
    assert decision_input.actor is ActorKind.SYSTEM


# --- Invalid payloads rejected (deny-by-default) --------------------------------


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        FirewallDecisionInput.model_validate(_decision_input_payload(bypass=True))


def test_llm_actor_rejected() -> None:
    with pytest.raises(ValidationError):
        FirewallDecisionInput.model_validate(_decision_input_payload(actor="llm"))


def test_invalid_approval_state_rejected() -> None:
    # Closed to approved|null — "pending"/"rejected" are not decision inputs.
    for bad in ("pending", "rejected", "denied"):
        with pytest.raises(ValidationError):
            FirewallDecisionInput.model_validate(_decision_input_payload(approval_state=bad))


def test_missing_required_input_rejected() -> None:
    # Every field in the documented example except approval_state is required.
    for required in (
        "actor",
        "tenant_id",
        "permission",
        "resource",
        "scope",
        "entitlement",
        "risk_level",
    ):
        payload = _decision_input_payload()
        del payload[required]
        with pytest.raises(ValidationError):
            FirewallDecisionInput.model_validate(payload)


def test_non_uuid_tenant_id_rejected() -> None:
    with pytest.raises(ValidationError):
        FirewallDecisionInput.model_validate(_decision_input_payload(tenant_id="not-a-uuid"))


def test_empty_permission_rejected() -> None:
    with pytest.raises(ValidationError):
        FirewallDecisionInput.model_validate(_decision_input_payload(permission=""))


def test_no_implicit_allow_decision_value() -> None:
    # Deny-by-default posture: no "DEFAULT"/"IMPLICIT" member exists.
    assert not {d.value for d in FirewallDecision} & {"DEFAULT", "IMPLICIT_ALLOW"}


# --- Value-object semantics ------------------------------------------------------


def test_decision_input_is_frozen() -> None:
    decision_input = FirewallDecisionInput.model_validate(_decision_input_payload())
    with pytest.raises(ValidationError):
        decision_input.permission = "github.repo.delete"  # type: ignore[misc]


def test_json_schema_export_is_closed() -> None:
    assert FirewallDecisionInput.model_json_schema()["additionalProperties"] is False
