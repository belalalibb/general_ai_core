"""R161 Phase 3 — part 3: self-evolution posture is STATED, in two lanes.

"Self-evolution" on this platform means exactly two things, and the
self-review report now names both with their gates instead of leaving
the reader to infer:

- KNOWLEDGE lane (open): captured → gated → GOLD → composer memory →
  ``/v1/execute`` answers, measured by ``context_provenance.gold_blocks``.
- SOURCE lane (§14-gated): R3 proposals act in the snapshot space only;
  ``authoritative_write`` is the workflow's OWN status — never paraphrased.

Pins:
- absent seams answer ``available: False`` (P6) — pre-R161 constructions
  stay valid verbatim (P2);
- the local runtime profile composes both lanes; the source lane quotes
  the §14 gate ``{"available": False, "gate": "S14_OPERATOR_GATE"}``;
- knowledge-lane counts move with the real lifecycle (capture → GOLD);
- ``auto_apply`` is ``never`` at both the section and posture level.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any
from uuid import UUID, uuid4

import httpx

from apps.api.self_review import SelfReviewService
from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.contracts.evaluation import VerificationLevel
from core.learning import EligibilitySignals, PromotionSignals

REVIEW = "/v1/admin/self-review"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _profile() -> RuntimeProfile:
    """Local profile with ONE admin listed — the same honest ADMIN_EMAILS
    composition fact the admin-console runtime tests use."""
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL

    return build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})


def _admin(profile: RuntimeProfile) -> tuple[dict[str, str], UUID]:
    """Register + verify + login the admin through the runtime's own identity."""
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL, PASSWORD, _admin_token

    token = _admin_token(profile)
    identity = profile.identity
    assert identity is not None
    session = identity.login(ADMIN_EMAIL, PASSWORD)
    return {"Authorization": f"Bearer {token}"}, session.tenant_id


async def _review(profile: RuntimeProfile, headers: dict[str, str]) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=profile.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get(REVIEW, headers=headers)
        assert response.status_code == 200, response.text
        return dict(response.json())


def _promote(profile: RuntimeProfile, tenant_id: UUID, key: str) -> None:
    service = profile.app.state.learning_lifecycle_service
    sample = service.capture_external(tenant_id, knowledge_key=key, knowledge_value={"v": key})
    service.mark_sanitized(tenant_id, sample.id, passed=True)
    service.set_verification_level(tenant_id, sample.id, VerificationLevel.VERIFIED)
    service.admit_to_training(
        tenant_id,
        sample.id,
        EligibilitySignals(
            privacy_policy_allows=True,
            tenant_user_policy_allows=True,
            sensitive_data_handled=True,
            not_poisoned=True,
        ),
    )
    service.promote_to_gold(
        tenant_id,
        sample.id,
        PromotionSignals(
            offline_eval_pass=True,
            regression_pass=True,
            security_eval_pass=True,
            shadow_performance_acceptable=True,
            canary_performance_acceptable=True,
            rollback_plan_exists=True,
            approval_required=True,
            admin_approved=True,
        ),
    )


class TestEvolutionSection:
    def test_absent_seams_answer_absent(self) -> None:
        review = SelfReviewService().self_review(uuid4())  # pre-R161 construction
        evolution = review["evolution"]
        assert evolution == {
            "knowledge_lane": {"available": False},
            "source_lane": {"available": False},
            "auto_apply": "never",
        }

    def test_local_profile_states_both_lanes_with_the_s14_gate(self) -> None:
        profile = _profile()
        headers, _ = _admin(profile)
        review = run(_review(profile, headers))
        evolution = review["evolution"]
        knowledge = evolution["knowledge_lane"]
        assert knowledge["available"] is True
        assert knowledge["samples"] == 0
        assert knowledge["gold_keys"] == []
        assert knowledge["reaches_production"]["measured_by"].endswith("gold_blocks")
        source = evolution["source_lane"]
        assert source["available"] is True
        assert source["proposals"] == 0
        assert source["apply_scope"].startswith("snapshot space only")
        # quoted from the workflow, not paraphrased — the §14 gate is named
        assert source["authoritative_write"] == {
            "available": False,
            "gate": "S14_OPERATOR_GATE",
        }
        assert evolution["auto_apply"] == "never"
        assert review["posture"]["auto_apply"] == "never"

    def test_knowledge_lane_counts_move_with_the_real_lifecycle(self) -> None:
        profile = _profile()
        headers, tenant = _admin(profile)
        _promote(profile, tenant, "ops.rollback")
        service = profile.app.state.learning_lifecycle_service
        service.capture_external(tenant, knowledge_key="pending.k", knowledge_value={"v": 1})
        knowledge = run(_review(profile, headers))["evolution"]["knowledge_lane"]
        assert knowledge["samples"] == 2
        assert knowledge["by_eligibility"] == {"eligible": 1, "pending": 1}
        assert knowledge["by_verification_level"]["GOLD"] == 1
        assert knowledge["gold_keys"] == ["ops.rollback"]

    def test_other_tenant_is_invisible(self) -> None:
        profile = _profile()
        headers, _ = _admin(profile)
        _promote(profile, uuid4(), "foreign.k")
        knowledge = run(_review(profile, headers))["evolution"]["knowledge_lane"]
        assert knowledge["samples"] == 0 and knowledge["gold_keys"] == []
