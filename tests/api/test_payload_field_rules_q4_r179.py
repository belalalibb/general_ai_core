"""R179 rulings Q4 (DEC-A) — ONE declared source of admin payload field rules.

Ruling: before the first UI form, the payload field rules must live in ONE
declared place that BOTH the validator (``core/admin/service.py``) and the shelf
(``apps/api/capabilities.py`` action discovery) read. No second list.

- ``PAYLOAD_FIELD_RULES`` maps EVERY ``AdminAction`` to a closed tuple of
  ``FieldRule`` rows (name, kind, required, contract). Presence/shape refusals
  in ``AdminConfigService._validation_problem`` are DERIVED from these rules
  (the semantic checks — "registered?", "template?", contract parse — stay
  imperative and run AFTER the declared rules hold).
- ``admin_actions_json()`` publishes the same rows per action under
  ``fields``; the ``actions`` rows keep ``action`` + ``area`` and gain ONLY
  ``fields``. The shelf row shape ``{id,state,evidence}`` is untouched.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from uuid import uuid4

import pytest

from apps.api.capabilities import admin_actions_json
from core.admin.service import (
    PAYLOAD_FIELD_KINDS,
    PAYLOAD_FIELD_RULES,
    FieldRule,
    field_rule_problem,
    field_rules_json,
)
from core.contracts.admin import AdminAction, ConfigLifecycleState
from tests.admin.test_final_admin_areas_t068 import ACTOR, TENANT, World

ROOT = Path(__file__).resolve().parents[2]


# --- the declared source -----------------------------------------------------------------


class TestDeclaredRules:
    def test_every_action_has_a_declared_rule_tuple(self) -> None:
        assert set(PAYLOAD_FIELD_RULES) == set(AdminAction)
        for action, rules in PAYLOAD_FIELD_RULES.items():
            assert isinstance(rules, tuple), action
            assert all(isinstance(rule, FieldRule) for rule in rules), action

    def test_rules_are_closed_frozen_rows_with_a_closed_kind_set(self) -> None:
        for rules in PAYLOAD_FIELD_RULES.values():
            for rule in rules:
                assert rule.kind in PAYLOAD_FIELD_KINDS, rule
                with pytest.raises(dataclasses.FrozenInstanceError):
                    rule.name = "x"  # type: ignore[misc]
            names = [rule.name for rule in rules]
            assert len(names) == len(set(names))  # no duplicate field per action

    def test_unknown_kind_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError):
            FieldRule("x", "blob")

    @pytest.mark.parametrize(
        ("action", "required"),
        [
            (AdminAction.ENABLE_MODEL, {"model_key"}),
            (AdminAction.DISABLE_MODEL, {"model_key"}),
            (AdminAction.ENABLE_PROVIDER, {"provider_key"}),
            (AdminAction.DISABLE_PROVIDER, {"provider_key"}),
            (AdminAction.ENABLE_SKILL, {"skill_id"}),
            (AdminAction.DISABLE_SKILL, {"skill_id"}),
            (AdminAction.SET_SKILL_SOURCES, {"urls"}),
            (AdminAction.ENABLE_TOOL, {"tool_id"}),
            (AdminAction.DISABLE_TOOL, {"tool_id"}),
            (AdminAction.REGISTER_PROVIDER, {"provider", "manifest"}),
            (AdminAction.REGISTER_MODEL, {"model"}),
            (AdminAction.SET_PLAN, {"target_tenant_id", "plan", "task_units_limit"}),
            (AdminAction.SET_ROUTING_WEIGHTS, {"weights"}),
        ],
    )
    def test_required_fields_match_the_validator_contract(
        self, action: AdminAction, required: set[str]
    ) -> None:
        declared = {r.name for r in PAYLOAD_FIELD_RULES[action] if r.required}
        assert declared == required

    def test_capability_proposal_is_declared_as_the_whole_sheet(self) -> None:
        rules = PAYLOAD_FIELD_RULES[AdminAction.CAPABILITY_PROPOSAL]
        names = {r.name for r in rules}
        assert {"proposal_id", "capability", "decision", "reason", "required"} <= names
        assert all(r.contract == "CapabilityProposalPayload" for r in rules)
        assert next(r for r in rules if r.name == "required").kind == "bool"

    def test_optional_fields_are_declared_not_hidden(self) -> None:
        optional = {
            (action, r.name)
            for action, rules in PAYLOAD_FIELD_RULES.items()
            for r in rules
            if not r.required
        }
        assert (AdminAction.SET_SKILL_SOURCES, "disabled") in optional
        assert (AdminAction.REGISTER_MODEL, "bindings") in optional


# --- the validator READS the rules -----------------------------------------------------


class TestValidatorReadsRules:
    def test_missing_required_field_is_refused_with_the_declared_name(self) -> None:
        for action, rules in PAYLOAD_FIELD_RULES.items():
            required = [r for r in rules if r.required]
            if not required or action is AdminAction.CAPABILITY_PROPOSAL:
                continue
            problem = field_rule_problem(action, {})
            assert problem is not None and required[0].name in problem, (action, problem)

    @pytest.mark.parametrize(
        ("action", "payload", "field"),
        [
            (AdminAction.ENABLE_MODEL, {"model_key": ""}, "model_key"),
            (AdminAction.ENABLE_MODEL, {"model_key": 3}, "model_key"),
            (AdminAction.ENABLE_SKILL, {"skill_id": "not-a-uuid"}, "skill_id"),
            (AdminAction.SET_SKILL_SOURCES, {"urls": "https://x"}, "urls"),
            (AdminAction.SET_SKILL_SOURCES, {"urls": []}, "urls"),
            (AdminAction.SET_SKILL_SOURCES, {"urls": ["https://x"], "disabled": "y"}, "disabled"),
            (AdminAction.REGISTER_PROVIDER, {"provider": [], "manifest": {}}, "provider"),
            (AdminAction.REGISTER_MODEL, {"model": {}, "bindings": {}}, "bindings"),
            (
                AdminAction.SET_PLAN,
                {"target_tenant_id": "x", "plan": "p", "task_units_limit": 1},
                "target_tenant_id",
            ),
            (
                AdminAction.SET_PLAN,
                {"target_tenant_id": str(uuid4()), "plan": "p", "task_units_limit": True},
                "task_units_limit",
            ),
            (
                AdminAction.SET_PLAN,
                {"target_tenant_id": str(uuid4()), "plan": "p", "task_units_limit": -1},
                "task_units_limit",
            ),
            (AdminAction.SET_ROUTING_WEIGHTS, {"weights": 1}, "weights"),
        ],
    )
    def test_shape_refusals_name_the_declared_field(
        self, action: AdminAction, payload: dict[str, object], field: str
    ) -> None:
        problem = field_rule_problem(action, payload)
        assert problem is not None and field in problem, problem

    def test_declared_rules_holding_returns_none(self) -> None:
        assert field_rule_problem(AdminAction.ENABLE_MODEL, {"model_key": "m"}) is None
        assert (
            field_rule_problem(
                AdminAction.SET_PLAN,
                {"target_tenant_id": str(uuid4()), "plan": "pro", "task_units_limit": 10},
            )
            is None
        )

    def test_service_validation_uses_the_declared_rules_first(self) -> None:
        world = World()
        change = world.service.draft(
            tenant_id=TENANT, actor_id=ACTOR, action=AdminAction.ENABLE_MODEL, payload={}
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED
        declared = field_rule_problem(AdminAction.ENABLE_MODEL, {})
        assert declared is not None
        assert (result.validation_result or "").endswith(declared)

    def test_service_source_has_no_inline_presence_checks_left(self) -> None:
        """The validator derives presence/shape from the table — no second list."""
        source = (ROOT / "core" / "admin" / "service.py").read_text(encoding="utf-8")
        body = source[source.index("def _validation_problem") :]
        body = body[: body.index("def _impact_preview")]
        # Every hand-written presence refusal is gone from the imperative half.
        assert "payload requires" not in body
        assert "is not a UUID" not in body
        assert "field_rule_problem(" in body

    def test_semantic_checks_still_run_after_the_declared_rules(self) -> None:
        world = World()
        change = world.service.draft(
            tenant_id=TENANT,
            actor_id=ACTOR,
            action=AdminAction.ENABLE_MODEL,
            payload={"model_key": "ghost"},
        )
        result = world.service.validate(TENANT, change.id)
        assert result.state is ConfigLifecycleState.REJECTED
        assert "not registered" in (result.validation_result or "")


# --- the shelf READS the same rules ---------------------------------------------------


class TestShelfReadsRules:
    def test_actions_rows_carry_the_declared_fields(self) -> None:
        payload = admin_actions_json()
        assert payload["field_rules"] == "core.admin.service.PAYLOAD_FIELD_RULES"
        for row in payload["actions"]:
            assert set(row) == {"action", "area", "fields"}
            action = AdminAction(row["action"])
            assert row["fields"] == field_rules_json(action)
            for field in row["fields"]:
                assert set(field) == {"name", "kind", "required", "contract"}
                assert field["kind"] in PAYLOAD_FIELD_KINDS

    def test_field_rules_json_is_a_pure_projection_of_the_table(self) -> None:
        for action, rules in PAYLOAD_FIELD_RULES.items():
            assert field_rules_json(action) == [
                {"name": r.name, "kind": r.kind, "required": r.required, "contract": r.contract}
                for r in rules
            ]

    def test_producer_still_has_no_hand_maintained_names(self) -> None:
        source = (ROOT / "apps" / "api" / "capabilities.py").read_text(encoding="utf-8")
        body = source[source.index("def admin_actions_json") :]
        literals = set(re.findall(r'"([a-z_]+)"', body))
        # Field NAMES never appear as literals in the producer (they come from the
        # table). The read model's own pre-existing keys ("capability", the shelf
        # link) are not field literals — the sheet column of the same spelling is
        # produced by field_rules_json, never typed here.
        field_names = {r.name for rules in PAYLOAD_FIELD_RULES.values() for r in rules}
        own_keys = {"scope", "capability", "vocabulary", "field_rules", "actions", "areas"}
        assert literals.isdisjoint(field_names - own_keys), literals & field_names
        assert "field_rules_json(action)" in body
        assert literals.isdisjoint({a.value for a in AdminAction}), literals

    def test_areas_rows_are_unchanged(self) -> None:
        for row in admin_actions_json()["areas"]:
            assert set(row) == {"area", "active", "actions"}
