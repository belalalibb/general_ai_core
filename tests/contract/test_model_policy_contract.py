"""Contract tests: advanced model control (10 §13) — all 5 policy types.

Every documented policy example from 10 §13.1-§13.5 is validated verbatim;
the closed sets (policy types, selection strategies, fallback scopes per 11 §8)
must match the spec exactly, and invalid payloads must be rejected.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from core.contracts.execute import ExecuteRequest
from core.contracts.model_policy import (
    AgentNodeMappingPolicy,
    AgentPolicy,
    ExplicitModelPolicy,
    ExplicitModelsPolicy,
    FallbackScope,
    ModelPolicy,
    SelectionStrategy,
    TierModelPolicy,
)

POLICY_ADAPTER: TypeAdapter[ModelPolicy] = TypeAdapter(ModelPolicy)


def test_policy_type_set_matches_spec_exactly() -> None:
    # 10 §13: auto / tier / explicit_model / explicit_models / agent_node_mapping.
    for policy_type, payload in {
        "auto": {"type": "auto"},
        "tier": {"type": "tier", "tier": "medium"},
        "explicit_model": {"type": "explicit_model", "model_id": "m"},
        "explicit_models": {"type": "explicit_models", "models": [{"model_id": "m"}]},
        "agent_node_mapping": {"type": "agent_node_mapping"},
    }.items():
        policy = POLICY_ADAPTER.validate_python(payload)
        assert policy.type == policy_type
    with pytest.raises(ValidationError):
        POLICY_ADAPTER.validate_python({"type": "made_up_policy"})


def test_selection_strategies_match_spec_exactly() -> None:
    # 10 §13.4 — verbatim, closed set.
    assert {s.value for s in SelectionStrategy} == {
        "fallback_chain",
        "parallel_compare",
        "best_of_n",
        "debate",
        "specialist_roles",
    }


def test_fallback_scopes_match_router_spec_exactly() -> None:
    # 11 §8 Fallback Policies — verbatim, closed set.
    assert {f.value for f in FallbackScope} == {
        "none",
        "same_model_different_provider",
        "same_tier",
        "lower_cost_same_capability",
        "max_escalation",
        "admin_defined_chain",
    }


def test_documented_auto_policy_validates() -> None:
    # The literal example from 10 §13.1.
    policy = POLICY_ADAPTER.validate_python(
        {"model_policy": {"type": "auto", "allow_fallback": True, "fallback_scope": "same_tier"}}[
            "model_policy"
        ]
    )
    assert policy.type == "auto"
    assert policy.fallback_scope is FallbackScope.SAME_TIER


def test_documented_tier_policy_validates() -> None:
    # The literal example from 10 §13.2.
    policy = TierModelPolicy.model_validate(
        {"type": "tier", "tier": "medium", "allow_fallback": True, "fallback_scope": "same_tier"}
    )
    assert policy.tier == "medium"
    # Tiers are admin-configurable (10 §13.2) — custom tier names must pass.
    assert TierModelPolicy.model_validate({"type": "tier", "tier": "custom_gpu_pool"})
    # But tier itself is required for type=tier.
    with pytest.raises(ValidationError):
        TierModelPolicy.model_validate({"type": "tier"})


def test_documented_explicit_model_policy_validates() -> None:
    # The literal example from 10 §13.3.
    payload = {
        "type": "explicit_model",
        "model_id": "model_coding_strong",
        "provider_id": None,
        "allow_fallback": False,
        "fallback_scope": "none",
    }
    policy = ExplicitModelPolicy.model_validate(payload)
    assert policy.model_id == "model_coding_strong"
    assert policy.provider_id is None  # Router may choose any eligible provider (rule 3)
    assert policy.model_dump(mode="json") == payload
    with pytest.raises(ValidationError):
        ExplicitModelPolicy.model_validate({"type": "explicit_model"})  # model_id required


def test_documented_explicit_models_policy_validates() -> None:
    # The literal example from 10 §13.4 (incl. nested judge_policy).
    payload = {
        "type": "explicit_models",
        "models": [
            {"model_id": "model_a", "provider_id": None},
            {"model_id": "model_b", "provider_id": None},
            {"model_id": "model_c", "provider_id": "provider_x"},
        ],
        "selection_strategy": "parallel_compare",
        "judge_policy": {"type": "tier", "tier": "max"},
        "allow_partial": True,
        "allow_fallback": True,
        "fallback_scope": "same_model_different_provider",
    }
    policy = ExplicitModelsPolicy.model_validate(payload)
    assert len(policy.models) == 3
    assert policy.models[2].provider_id == "provider_x"
    assert policy.selection_strategy is SelectionStrategy.PARALLEL_COMPARE
    assert policy.judge_policy is not None and policy.judge_policy.type == "tier"


def test_explicit_models_requires_nonempty_list() -> None:
    with pytest.raises(ValidationError):
        ExplicitModelsPolicy.model_validate({"type": "explicit_models", "models": []})


def test_documented_agent_node_mapping_validates() -> None:
    # The literal agent_policy example from 10 §13.5 (request-level carrier).
    agent_policy = AgentPolicy.model_validate(
        {
            "workflow": "code_review_and_patch",
            "default_model_policy": {"type": "tier", "tier": "medium"},
            "node_model_policies": {
                "planner": {"type": "tier", "tier": "medium"},
                "code_analyzer": {
                    "type": "explicit_model",
                    "model_id": "model_coding_strong",
                    "allow_fallback": True,
                    "fallback_scope": "same_model_different_provider",
                },
                "patch_generator": {
                    "type": "explicit_model",
                    "model_id": "model_coding_fast",
                },
                "security_reviewer": {"type": "tier", "tier": "max"},
                "final_judge": {
                    "type": "explicit_models",
                    "models": [{"model_id": "judge_a"}, {"model_id": "judge_b"}],
                    "selection_strategy": "parallel_compare",
                },
            },
        }
    )
    assert agent_policy.workflow == "code_review_and_patch"
    assert set(agent_policy.node_model_policies) == {
        "planner",
        "code_analyzer",
        "patch_generator",
        "security_reviewer",
        "final_judge",
    }
    final_judge = agent_policy.node_model_policies["final_judge"]
    assert final_judge.type == "explicit_models"

    # Full documented request shape: mode=agent + agent_policy.
    req = ExecuteRequest.model_validate(
        {
            "ask": "review and patch this repo",
            "mode": "agent",
            "agent_policy": agent_policy.model_dump(mode="json", by_alias=True),
        }
    )
    assert req.agent_policy is not None
    assert req.agent_policy.default_model_policy is not None


def test_agent_node_mapping_as_model_policy_type() -> None:
    # The 5th model_policy type per the 10 §13 supported-types list.
    policy = AgentNodeMappingPolicy.model_validate(
        {
            "type": "agent_node_mapping",
            "default_model_policy": {"type": "auto"},
            "node_model_policies": {"planner": {"type": "tier", "tier": "medium"}},
        }
    )
    assert policy.default_model_policy is not None
    assert policy.node_model_policies["planner"].type == "tier"
    # Node-level policies do not admit agent_node_mapping recursively (10 §13.5
    # node policies are auto/tier/explicit_model/explicit_models).
    with pytest.raises(ValidationError):
        AgentNodeMappingPolicy.model_validate(
            {
                "type": "agent_node_mapping",
                "node_model_policies": {"planner": {"type": "agent_node_mapping"}},
            }
        )


def test_auto_policy_explicit_model_id_must_be_null() -> None:
    # 10 §2 shows explicit_model_id: null on type=auto; a concrete model id
    # on an auto policy is a contradiction and must be rejected.
    with pytest.raises(ValidationError):
        POLICY_ADAPTER.validate_python({"type": "auto", "explicit_model_id": "model_x"})


def test_unknown_fallback_scope_rejected() -> None:
    with pytest.raises(ValidationError):
        POLICY_ADAPTER.validate_python({"type": "auto", "fallback_scope": "teleport"})


def test_policy_json_schema_export() -> None:
    schema = POLICY_ADAPTER.json_schema()
    # Discriminated union over exactly the 5 documented policy types.
    mapping = schema["discriminator"]["mapping"]
    assert set(mapping) == {
        "auto",
        "tier",
        "explicit_model",
        "explicit_models",
        "agent_node_mapping",
    }
