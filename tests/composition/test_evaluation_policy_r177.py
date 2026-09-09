"""R177-FIX-09 — compose the model judge behind a 22 §10 selection policy (G-A07-2).

Before: ``AdapterModelJudge`` existed in core but no composition bound it, so
VERIFIED ("sufficient evidence/confidence", 22 §3) was unreachable through
``evaluate()``. After: ``apps/composition/evaluation_policy.py`` composes the
EXISTING judge over the EXISTING adapter/binding registries ONLY when the
operator sets ``EVAL_JUDGE_MODEL_POLICY``, and wraps it in a selector that
runs the judge for the 22 §10 categories ONLY (high-value / uncertain / new
task category / calibration set / canary) — "not every request needs teacher
review". Disabled ⇒ today's behaviour byte-identical (level ≤ VALIDATED).

Judge failures still raise ``JudgeFailure`` inside the policy service's single
containment point; a NOT-SELECTED sample is skipped the same way (deterministic
only), never given a fabricated judgment.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from apps.composition.evaluation_policy import (
    ENV_JUDGE_POLICY,
    JudgeSelectionPolicy,
    SelectiveModelJudge,
    build_selective_judge,
    parse_judge_policy,
)

from core.contracts.base import JsonObject
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    Provider,
    ProviderModelBinding,
    ProviderStatus,
)
from core.contracts.evaluation import GraderResult, GraderType, VerificationLevel
from core.contracts.provider import (
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderManifest,
)
from core.evaluation.errors import JudgeFailure
from core.evaluation.memory import InMemoryEvaluationStore
from core.evaluation.policy import EvaluationPolicyService
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry

TENANT = uuid4()


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


class RecordingJudge:
    """Inner judge that records calls and answers a fixed judgment."""

    def __init__(self, score: float = 0.9, confidence: float = 0.9) -> None:
        self.calls: list[UUID] = []
        self._score = score
        self._confidence = confidence

    async def judge(self, tenant_id: UUID, execution_id: UUID, output: JsonObject) -> GraderResult:
        self.calls.append(execution_id)
        return GraderResult(
            type=GraderType.MODEL_BASED,
            name="teacher",
            score=self._score,
            confidence=self._confidence,
        )


def _policy(**overrides: Any) -> JudgeSelectionPolicy:
    values: dict[str, Any] = {
        "uncertain_below": 0.6,
        "new_categories": frozenset({"legal.contracts"}),
        "calibration_keys": frozenset({"calib-1"}),
        "canary": True,
        "high_value": True,
    }
    values.update(overrides)
    return JudgeSelectionPolicy(**values)


GOOD = {"content": "answer", "error": None}


# --- selection (22 §10 list, verbatim categories) ------------------------------------------


class TestSelection:
    def test_plain_output_is_not_selected(self) -> None:
        assert _policy().selects(GOOD) is None

    def test_each_22_10_category_selects_with_its_named_reason(self) -> None:
        policy = _policy()
        cases = {
            "uncertain": {**GOOD, "confidence": 0.3},
            "new_task_category": {**GOOD, "task_category": "legal.contracts"},
            "calibration_set": {**GOOD, "calibration_set": "calib-1"},
            "canary": {**GOOD, "canary": True},
            "high_value": {**GOOD, "high_value": True},
        }
        for reason, output in cases.items():
            assert policy.selects(output) == reason, reason

    def test_categories_are_data_not_defaults(self) -> None:
        # Unknown category / other calibration set / canary disabled ⇒ not selected.
        policy = _policy(canary=False, high_value=False)
        assert policy.selects({**GOOD, "task_category": "faq"}) is None
        assert policy.selects({**GOOD, "calibration_set": "calib-9"}) is None
        assert policy.selects({**GOOD, "canary": True}) is None
        assert policy.selects({**GOOD, "high_value": True}) is None
        # Confidence at/above the threshold is NOT uncertain.
        assert policy.selects({**GOOD, "confidence": 0.6}) is None
        # Non-numeric confidence is ignored, never coerced.
        assert policy.selects({**GOOD, "confidence": "low"}) is None

    def test_reasons_are_the_closed_22_10_list(self) -> None:
        assert JudgeSelectionPolicy.REASONS == (
            "high_value",
            "uncertain",
            "new_task_category",
            "calibration_set",
            "canary",
        )


# --- selective judge inside the EXISTING policy service ------------------------------------


class TestSelectiveJudgeInPipeline:
    def _service(self, inner: RecordingJudge, policy: JudgeSelectionPolicy | None = None):
        judge = SelectiveModelJudge(inner=inner, policy=policy or _policy())
        return EvaluationPolicyService(store=InMemoryEvaluationStore(), judge=judge), judge

    def test_not_selected_stays_deterministic_only_level_capped_validated(self) -> None:
        inner = RecordingJudge()
        service, judge = self._service(inner)
        record = run(service.evaluate(TENANT, uuid4(), GOOD))
        assert inner.calls == []
        assert record.level is VerificationLevel.VALIDATED
        assert all(g.type is GraderType.DETERMINISTIC for g in record.graders)
        assert judge.skipped == 1 and judge.judged == 0

    def test_selected_sample_reaches_verified_through_the_judge(self) -> None:
        inner = RecordingJudge(score=0.9, confidence=0.9)
        service, judge = self._service(inner)
        execution_id = uuid4()
        record = run(service.evaluate(TENANT, execution_id, {**GOOD, "canary": True}))
        assert inner.calls == [execution_id]
        assert record.level is VerificationLevel.VERIFIED
        judged = [g for g in record.graders if g.type is GraderType.MODEL_BASED]
        assert len(judged) == 1 and judged[0].name == "teacher"
        assert judge.judged == 1 and judge.last_reason == "canary"

    def test_low_confidence_judgment_never_fakes_verified(self) -> None:
        inner = RecordingJudge(score=0.9, confidence=0.4)
        service, _ = self._service(inner)
        record = run(service.evaluate(TENANT, uuid4(), {**GOOD, "canary": True}))
        assert record.level is VerificationLevel.VALIDATED  # judged but below the VERIFIED bar

    def test_skip_is_a_judge_failure_not_a_fabricated_row(self) -> None:
        judge = SelectiveModelJudge(inner=RecordingJudge(), policy=_policy())
        with pytest.raises(JudgeFailure, match="not selected"):
            run(judge.judge(TENANT, uuid4(), GOOD))


# --- env parsing + composition over EXISTING registries ------------------------------------


class TestEnvComposition:
    def test_env_name_is_the_approved_one(self) -> None:
        assert ENV_JUDGE_POLICY == "EVAL_JUDGE_MODEL_POLICY"

    def test_unset_means_no_judge(self) -> None:
        assert parse_judge_policy({}) is None
        assert parse_judge_policy({ENV_JUDGE_POLICY: ""}) is None

    def test_policy_grammar(self) -> None:
        raw = "judge-model;uncertain_below=0.5;new=legal.contracts,tax;calibration=c1;canary=0"
        spec = parse_judge_policy({ENV_JUDGE_POLICY: raw})
        assert spec is not None
        assert spec.model_key == "judge-model"
        assert spec.policy.uncertain_below == 0.5
        assert spec.policy.new_categories == frozenset({"legal.contracts", "tax"})
        assert spec.policy.calibration_keys == frozenset({"c1"})
        assert spec.policy.canary is False
        assert spec.policy.high_value is True  # default on

    def test_malformed_policy_is_refused_loudly(self) -> None:
        for bad in (
            ";uncertain_below=0.5",
            "m;uncertain_below=abc",
            "m;bogus=1",
            "m;uncertain_below=1.5",
        ):
            with pytest.raises(ValueError):
                parse_judge_policy({ENV_JUDGE_POLICY: bad})

    def _registries(
        self,
    ) -> tuple[ProviderRegistry, ModelRegistry, BindingRegistry, Provider, Model]:
        providers, models, bindings = ProviderRegistry(), ModelRegistry(), BindingRegistry()
        provider = Provider(
            id=uuid4(),
            provider_key="prov_j",
            display_name="J",
            status=ProviderStatus.ACTIVE,
            auth_types=["api_key"],
            supports_account_pool=False,
        )
        providers.register(
            provider,
            ProviderManifest.model_validate(
                {
                    "id": "prov_j",
                    "name": "prov_j",
                    "version": "1.0.0",
                    "status": "active",
                    "auth": {"types": ["api_key"], "supports_refresh": False},
                    "account_pool": {"supported": False},
                    "capabilities": {"chat": True},
                    "operations": ["generate_text"],
                    "models": {"discovery": "static", "static_models": []},
                    "rate_limits": {"strategy": "provider_defined"},
                    "health": {"checks": ["ping"]},
                    "errors": {"mapping": "error_map.json"},
                }
            ),
        )
        model = Model(
            id=uuid4(),
            model_key="judge-model",
            display_name="Judge",
            tier=ModelTier.MAX,
            modalities=["text"],
            capabilities=["reasoning"],
            quality_score=0.9,
            reliability_score=0.9,
            cost_score=0.2,
            speed_score=0.5,
            status=ModelStatus.ACTIVE,
        )
        models.register(model)
        bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=model.id,
                provider_model_name="vendor/judge",
                availability=BindingAvailability.AVAILABLE,
            )
        )
        return providers, models, bindings, provider, model

    def test_composes_adapter_model_judge_over_existing_bindings(self) -> None:
        providers, models, bindings, provider, _ = self._registries()

        class JudgeAdapter:
            async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
                assert request.provider_model_name == "vendor/judge"
                assert request.credential_ref == "secret-ref://j"
                return ProviderGenerateResponse(
                    request_id=request.request_id,
                    succeeded=True,
                    output={"score": 0.9, "confidence": 0.95},
                    usage={"units": 1},
                    latency_ms=1,
                )

            async def health_check(self, scope: object) -> object:  # pragma: no cover
                raise NotImplementedError

            def normalize_error(self, error: object) -> ProviderError:  # pragma: no cover
                return ProviderError(
                    category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
                    retryable=False,
                    safe_message="x",
                )

        judge = build_selective_judge(
            {ENV_JUDGE_POLICY: "judge-model;canary=1"},
            providers=providers,
            models=models,
            bindings=bindings,
            adapters={provider.id: JudgeAdapter()},
            credential_refs={provider.id: "secret-ref://j"},
        )
        assert judge is not None
        service = EvaluationPolicyService(store=InMemoryEvaluationStore(), judge=judge)
        record = run(service.evaluate(TENANT, uuid4(), {**GOOD, "canary": True}))
        assert record.level is VerificationLevel.VERIFIED
        plain = run(service.evaluate(TENANT, uuid4(), GOOD))
        assert plain.level is VerificationLevel.VALIDATED

    def test_unset_env_composes_nothing(self) -> None:
        providers, models, bindings, provider, _ = self._registries()
        assert (
            build_selective_judge(
                {},
                providers=providers,
                models=models,
                bindings=bindings,
                adapters={},
                credential_refs={},
            )
            is None
        )

    def test_unknown_model_or_unbound_adapter_is_refused_not_silently_absent(self) -> None:
        providers, models, bindings, provider, _ = self._registries()
        with pytest.raises(ValueError, match="not registered"):
            build_selective_judge(
                {ENV_JUDGE_POLICY: "nope"},
                providers=providers,
                models=models,
                bindings=bindings,
                adapters={},
                credential_refs={},
            )
        with pytest.raises(ValueError, match="no bound adapter"):
            build_selective_judge(
                {ENV_JUDGE_POLICY: "judge-model"},
                providers=providers,
                models=models,
                bindings=bindings,
                adapters={},
                credential_refs={},
            )


# --- wiring pins ---------------------------------------------------------------------------


def test_app_exposes_an_evaluation_judge_seam_and_runtime_passes_it() -> None:
    app_source = Path("apps/api/app.py").read_text(encoding="utf-8")
    assert "evaluation_judge: ModelJudgePort | None = None" in app_source
    assert "judge=evaluation_judge" in app_source
    runtime_source = Path("apps/composition/runtime.py").read_text(encoding="utf-8")
    assert "build_selective_judge(" in runtime_source
    assert "evaluation_judge=evaluation_judge" in runtime_source
