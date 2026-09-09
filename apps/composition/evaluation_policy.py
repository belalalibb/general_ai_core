"""Selective model-judge composition — 22 §10 "Teacher Model Policy" (R177-FIX-09).

Closes G-A07-2: ``AdapterModelJudge`` (core/evaluation/policy.py) had a seam
but no composition, so VERIFIED (22 §3 "sufficient evidence/confidence") was
unreachable through ``evaluate()``. This module binds the EXISTING judge over
the EXISTING provider adapter / binding registries — ONLY when the operator
sets ``EVAL_JUDGE_MODEL_POLICY`` — and wraps it in a selector that applies
22 §10 verbatim: "Max/teacher models are used selectively: high-value
samples / uncertain samples / new task categories / calibration sets /
canary evaluation. Not every request needs teacher review."

Recorded decisions:

- DISABLED = TODAY. No env value ⇒ ``build_selective_judge`` returns None ⇒
  the policy service runs deterministic-only and the level ladder caps at
  VALIDATED exactly as before (byte-identical behaviour, A07 §2).
- SELECTION IS DATA read from the execution OUTPUT (the only thing the judge
  seam receives): ``confidence`` below the threshold ⇒ uncertain;
  ``task_category`` in the declared new-category set; ``calibration_set`` in
  the declared set; ``canary: true``; ``high_value: true``. Categories not
  declared are not selected — nothing is inferred.
- A NOT-SELECTED sample raises :class:`JudgeFailure` ("not selected") so the
  policy service's SINGLE containment point degrades it to deterministic-only.
  No fabricated judgment row, no fake level (41 §49).
- COST STAYS VISIBLE: the composed judge routes through the SAME adapter the
  execution service uses for that provider (paid inference), which is why
  selection is mandatory and the model must be explicitly named.
- MISCONFIGURATION IS LOUD: an unknown model key, an unbound adapter, or a
  malformed policy string raises ``ValueError`` at composition — never a
  silently absent judge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar
from uuid import UUID

from core.contracts.base import JsonObject
from core.contracts.domain import BindingAvailability
from core.contracts.evaluation import GraderResult
from core.evaluation.errors import JudgeFailure
from core.evaluation.policy import AdapterModelJudge, ModelJudgePort
from core.providers.errors import ModelNotRegistered
from core.providers.ports import ProviderAdapterPort
from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry

__all__ = [
    "ENV_JUDGE_POLICY",
    "JudgePolicySpec",
    "JudgeSelectionPolicy",
    "SelectiveModelJudge",
    "build_selective_judge",
    "parse_judge_policy",
]

#: Operator switch (assessment §11 FIX-09). Grammar (``;``-separated):
#: ``<model_key>`` then optional ``uncertain_below=<0..1>``, ``new=<cat,cat>``,
#: ``calibration=<key,key>``, ``canary=0|1``, ``high_value=0|1``.
ENV_JUDGE_POLICY = "EVAL_JUDGE_MODEL_POLICY"


@dataclass(frozen=True)
class JudgeSelectionPolicy:
    """Which samples get teacher review — the 22 §10 list as composition data."""

    #: 22 §10 categories, verbatim order; ``selects`` returns one of these.
    REASONS: ClassVar[tuple[str, ...]] = (
        "high_value",
        "uncertain",
        "new_task_category",
        "calibration_set",
        "canary",
    )

    uncertain_below: float = 0.5
    new_categories: frozenset[str] = frozenset()
    calibration_keys: frozenset[str] = frozenset()
    canary: bool = True
    high_value: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= self.uncertain_below <= 1.0:
            msg = "uncertain_below must be within [0, 1]"
            raise ValueError(msg)

    def selects(self, output: JsonObject) -> str | None:
        """Return the 22 §10 reason that selects ``output``, or None."""
        if self.high_value and output.get("high_value") is True:
            return "high_value"
        confidence = output.get("confidence")
        if (
            isinstance(confidence, int | float)
            and not isinstance(confidence, bool)
            and float(confidence) < self.uncertain_below
        ):
            return "uncertain"
        category = output.get("task_category")
        if isinstance(category, str) and category in self.new_categories:
            return "new_task_category"
        calibration = output.get("calibration_set")
        if isinstance(calibration, str) and calibration in self.calibration_keys:
            return "calibration_set"
        if self.canary and output.get("canary") is True:
            return "canary"
        return None


class SelectiveModelJudge:
    """``ModelJudgePort`` that consults the policy before spending a judge call."""

    def __init__(self, *, inner: ModelJudgePort, policy: JudgeSelectionPolicy) -> None:
        self._inner = inner
        self._policy = policy
        self.judged = 0
        self.skipped = 0
        self.last_reason: str | None = None

    async def judge(self, tenant_id: UUID, execution_id: UUID, output: JsonObject) -> GraderResult:
        reason = self._policy.selects(output)
        if reason is None:
            self.skipped += 1
            raise JudgeFailure("not selected for teacher review (22 §10)")
        self.judged += 1
        self.last_reason = reason
        return await self._inner.judge(tenant_id, execution_id, output)


@dataclass(frozen=True)
class JudgePolicySpec:
    model_key: str
    policy: JudgeSelectionPolicy


def _flag(raw: str, key: str) -> bool:
    if raw in ("0", "1"):
        return raw == "1"
    msg = f"{ENV_JUDGE_POLICY}: {key} must be 0 or 1"
    raise ValueError(msg)


def parse_judge_policy(env: Mapping[str, str]) -> JudgePolicySpec | None:
    """Parse ``EVAL_JUDGE_MODEL_POLICY``; None when unset/empty; ValueError when malformed."""
    raw = env.get(ENV_JUDGE_POLICY, "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(";")]
    model_key = parts[0]
    if not model_key:
        msg = f"{ENV_JUDGE_POLICY}: model key is required before the first ';'"
        raise ValueError(msg)
    values: dict[str, object] = {}
    for part in parts[1:]:
        if not part:
            continue
        key, sep, value = part.partition("=")
        if not sep:
            msg = f"{ENV_JUDGE_POLICY}: expected key=value, got {part!r}"
            raise ValueError(msg)
        if key == "uncertain_below":
            try:
                values[key] = float(value)
            except ValueError as exc:
                msg = f"{ENV_JUDGE_POLICY}: uncertain_below is not a number"
                raise ValueError(msg) from exc
        elif key == "new":
            values["new_categories"] = frozenset(c for c in value.split(",") if c)
        elif key == "calibration":
            values["calibration_keys"] = frozenset(c for c in value.split(",") if c)
        elif key in ("canary", "high_value"):
            values[key] = _flag(value, key)
        else:
            msg = f"{ENV_JUDGE_POLICY}: unknown policy key {key!r}"
            raise ValueError(msg)
    return JudgePolicySpec(model_key=model_key, policy=JudgeSelectionPolicy(**values))  # type: ignore[arg-type]


def build_selective_judge(
    env: Mapping[str, str],
    *,
    providers: ProviderRegistry,
    models: ModelRegistry,
    bindings: BindingRegistry,
    adapters: Mapping[UUID, ProviderAdapterPort],
    credential_refs: Mapping[UUID, str],
) -> SelectiveModelJudge | None:
    """Compose the judge over EXISTING registries; None when the switch is unset.

    The judge model is resolved like any routed model: registered ``Model``
    → an AVAILABLE ``ProviderModelBinding`` whose provider has a bound
    adapter + credential ref. The first such binding is used (recorded:
    no scoring here — the operator named ONE model deliberately).
    """
    spec = parse_judge_policy(env)
    if spec is None:
        return None
    try:
        model = models.get(spec.model_key)
    except ModelNotRegistered as exc:
        msg = f"{ENV_JUDGE_POLICY}: judge model not registered: {spec.model_key!r}"
        raise ValueError(msg) from exc
    for binding in bindings.bindings_for_model(model.id):
        if binding.availability is not BindingAvailability.AVAILABLE:
            continue
        adapter = adapters.get(binding.provider_id)
        credential_ref = credential_refs.get(binding.provider_id)
        if adapter is None or credential_ref is None:
            continue
        providers.get_by_id(binding.provider_id)  # must still be registered
        inner = AdapterModelJudge(
            adapter,
            provider_model_name=binding.provider_model_name,
            credential_ref=credential_ref,
            judge_name=f"teacher:{spec.model_key}",
        )
        return SelectiveModelJudge(inner=inner, policy=spec.policy)
    msg = (
        f"{ENV_JUDGE_POLICY}: no bound adapter with an AVAILABLE binding for "
        f"judge model {spec.model_key!r}"
    )
    raise ValueError(msg)
