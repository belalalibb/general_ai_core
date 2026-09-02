"""Learning lifecycle service — R158 (connects EXISTING pieces; builds none).

Platform-consolidation finding (evidence): every stage of the 22 §8
lifecycle already exists as a verified component, but NOTHING connects
them — the pipeline was contracts + gates with no operator:

- capture:      LearningSample contract (core/contracts/learning.py) — no
                producer anywhere (grep: only gates + observability import it).
- evaluation:   EvaluationPolicyService (core/evaluation/policy.py) — wired
                for execute-path grading, never for samples.
- eligibility:  TrainingEligibilityGate (core/learning/gates.py) — pure,
                zero callers outside tests.
- promotion:    PromotionGate (core/learning/gates.py) — zero callers;
                AuditEventType.TRAINING_DATASET_PROMOTED (20 §9) exists in
                the closed audit set but is EMITTED NOWHERE (grep-verified).
- retrieval:    MemoryStorePort / InMemoryMemoryStore (core/memory) — the
                platform's existing retrieval substrate; GOLD knowledge has
                no writer into it.

This service is the smallest connection: ONE tenant-scoped operator over
those exact components. It owns NO new stage, NO new store type, NO new
telemetry — promotion emits the EXISTING audit event; retrieval writes
through the EXISTING memory port (scope=TENANT, source=learning.gold);
evaluation delegates verbatim to the EXISTING policy service.

Recorded design decisions:

- SAMPLE STATE lives here in a tenant-keyed in-process map (same posture
  as InMemoryEvaluationStore / ScenarioService: durable binding is a
  later conscious slice; the SHAPE is the frozen contract).
- TENANT ISOLATION: every read/write is keyed (tenant_id, sample_id);
  absent and foreign-tenant ids are the SAME error (anti-enumeration,
  20 §6 posture — mirrors ScenarioService).
- CAPTURE is deny-by-default BY CONTRACT: a new sample enters PENDING/
  PENDING/RAW (LearningSample defaults) — nothing is eligible on entry.
- EXTERNAL DATA (41-pack future-ready requirement) enters through the
  SAME pipeline: ``capture_external`` creates the same PENDING sample and
  never grants trust — review/evaluation/gates apply identically. The
  only difference is provenance recorded in the sample map (source kind),
  because the CONTRACT has no provenance field and inventing one silently
  is forbidden; the honest carrier is service-level metadata.
- EVALUATE binds the sample's verification_level to the EvaluationRecord
  the EXISTING policy service produced for the sample's source execution
  — one grader pipeline, two consumers (execute path + learning path).
- SANITIZATION: the spec (22 §8) places sanitization before evaluation;
  no sanitizer machinery exists in the repo (verified). The honest seam
  is ``mark_sanitized(passed=...)`` — an explicit reviewed ACT recorded
  on the sample, exactly like skill-import review steps. The gate then
  consumes the state; nothing passes silently.
- GOLD PROMOTION runs BOTH existing gates in order (eligibility, then
  promotion). Success = verification_level GOLD + the 20 §9 audit event
  + the knowledge write into memory. Failure = the gates' own loud,
  every-condition-named errors — this service adds no verdict logic.
- ISOLATED TEST PATH: ``ask_learned`` answers ONLY from GOLD knowledge
  (memory items with source=learning.gold) — it touches no conversation
  store, no execution path, no production chat state. Deny-by-default:
  no GOLD match = an explicit not-found answer, never a fabricated one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from core.contracts.audit import AuditEvent, AuditEventType
from core.contracts.base import JsonObject, utc_now
from core.contracts.evaluation import VerificationLevel
from core.contracts.learning import (
    LearningEligibility,
    LearningSample,
    SanitizationState,
)
from core.contracts.memory import MemoryItem, MemoryScope
from core.learning.errors import LearningError
from core.learning.gates import (
    EligibilitySignals,
    PromotionGate,
    PromotionSignals,
    TrainingEligibilityGate,
)

#: The machine-checkable source label GOLD knowledge carries in memory —
#: the isolated test path answers ONLY from items with this source.
GOLD_KNOWLEDGE_SOURCE = "learning.gold"


class SampleNotFound(LearningError):
    """Absent and foreign-tenant sample ids are the same answer (20 §6)."""

    def __init__(self, sample_id: UUID) -> None:
        super().__init__(f"learning sample not found: {sample_id}")
        self.sample_id = sample_id


class SampleSource(StrEnum):
    """Provenance kind (service metadata — the frozen contract carries none)."""

    EXECUTION = "execution"
    EXTERNAL = "external"


class EvaluationRunner(Protocol):
    """The EXISTING evaluation seam this service delegates to (P2).

    Matches ``EvaluationPolicyService.evaluate`` — the learning path is a
    second consumer of the SAME grader pipeline, never a parallel one.
    """

    async def evaluate(self, tenant_id: UUID, execution_id: UUID, output: JsonObject) -> object: ...


class KnowledgeStorePort(Protocol):
    """The EXISTING memory-store seam (core/memory/ports.py subset used)."""

    def upsert(self, item: MemoryItem) -> MemoryItem: ...

    def query(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        scope: object | None = None,
        key: str | None = None,
        min_confidence: float = 0.0,
        include_expired: bool = False,
    ) -> tuple[MemoryItem, ...]: ...


class AuditPort(Protocol):
    """The EXISTING audit-log seam (core/audit)."""

    def append(self, event: AuditEvent) -> AuditEvent: ...


@dataclass(frozen=True)
class CapabilitySnapshot:
    """One measured pass over a fixed probe set (R160 re-test)."""

    probes: tuple[str, ...]
    found: tuple[str, ...]
    missing: tuple[str, ...]
    taken_at: datetime

    @property
    def score(self) -> float:
        return len(self.found) / len(self.probes) if self.probes else 0.0

    def as_json(self) -> JsonObject:
        return {
            "probes": list(self.probes),
            "found": list(self.found),
            "missing": list(self.missing),
            "score": self.score,
            "taken_at": self.taken_at.isoformat(),
        }


@dataclass
class _SampleRecord:
    """One tracked sample: frozen contract + service-level metadata."""

    sample: LearningSample
    source_kind: SampleSource
    knowledge_key: str
    knowledge_value: JsonObject
    eligibility_verdicts: dict[str, bool] = field(default_factory=dict)
    promotion_verdicts: dict[str, bool] = field(default_factory=dict)


class LearningLifecycleService:
    """22 §8 lifecycle operator over the EXISTING components — nothing new.

    capture → (sanitize: explicit act) → evaluate (existing pipeline) →
    eligibility gate (existing) → promotion gate (existing) → GOLD →
    retrieval write (existing memory port) → isolated test path.
    """

    def __init__(
        self,
        *,
        evaluation: EvaluationRunner | None = None,
        knowledge: KnowledgeStorePort,
        audit: AuditPort | None = None,
        eligibility_gate: TrainingEligibilityGate | None = None,
        promotion_gate: PromotionGate | None = None,
    ) -> None:
        self._evaluation = evaluation
        self._knowledge = knowledge
        self._audit = audit
        self._eligibility = eligibility_gate or TrainingEligibilityGate()
        self._promotion = promotion_gate or PromotionGate()
        self._samples: dict[tuple[UUID, UUID], _SampleRecord] = {}

    # --- capture (deny-by-default by contract) --------------------------------

    def capture_from_execution(
        self,
        tenant_id: UUID,
        source_execution_id: UUID,
        *,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> LearningSample:
        """Track one execution-born candidate — PENDING everything."""
        return self._capture(
            tenant_id,
            source_execution_id,
            SampleSource.EXECUTION,
            knowledge_key,
            knowledge_value,
        )

    def capture_external(
        self,
        tenant_id: UUID,
        *,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> LearningSample:
        """External data enters the SAME pipeline — never trusted on entry.

        The synthetic source_execution_id marks the ingestion act itself;
        provenance kind EXTERNAL rides service metadata (recorded above).
        """
        return self._capture(
            tenant_id,
            uuid4(),
            SampleSource.EXTERNAL,
            knowledge_key,
            knowledge_value,
        )

    def _capture(
        self,
        tenant_id: UUID,
        source_execution_id: UUID,
        kind: SampleSource,
        knowledge_key: str,
        knowledge_value: JsonObject,
    ) -> LearningSample:
        sample = LearningSample(
            id=uuid4(),
            source_execution_id=source_execution_id,
            tenant_id=tenant_id,
        )  # contract defaults: PENDING / PENDING / RAW / no dataset
        self._samples[(tenant_id, sample.id)] = _SampleRecord(
            sample=sample,
            source_kind=kind,
            knowledge_key=knowledge_key,
            knowledge_value=knowledge_value,
        )
        return sample

    # --- reads (tenant-scoped, anti-enumeration) -------------------------------

    def get(self, tenant_id: UUID, sample_id: UUID) -> LearningSample:
        return self._record(tenant_id, sample_id).sample

    def list_samples(self, tenant_id: UUID) -> tuple[LearningSample, ...]:
        return tuple(
            record.sample for (owner, _), record in self._samples.items() if owner == tenant_id
        )

    def sample_report(self, tenant_id: UUID, sample_id: UUID) -> JsonObject:
        """One sample's full lifecycle state — evidence for the admin surface."""
        record = self._record(tenant_id, sample_id)
        return {
            "sample": record.sample.model_dump(mode="json"),
            "source_kind": record.source_kind.value,
            "knowledge_key": record.knowledge_key,
            "eligibility_verdicts": dict(record.eligibility_verdicts),
            "promotion_verdicts": dict(record.promotion_verdicts),
        }

    def _record(self, tenant_id: UUID, sample_id: UUID) -> _SampleRecord:
        record = self._samples.get((tenant_id, sample_id))
        if record is None:  # absent == foreign-tenant (same answer)
            raise SampleNotFound(sample_id)
        return record

    # --- sanitization (explicit reviewed act; no silent pass) -------------------

    def mark_sanitized(self, tenant_id: UUID, sample_id: UUID, *, passed: bool) -> LearningSample:
        record = self._record(tenant_id, sample_id)
        record.sample = record.sample.model_copy(
            update={
                "sanitization_state": (
                    SanitizationState.PASSED if passed else SanitizationState.FAILED
                )
            }
        )
        return record.sample

    # --- evaluation (delegates to the EXISTING pipeline) ------------------------

    async def evaluate(
        self, tenant_id: UUID, sample_id: UUID, output: JsonObject
    ) -> LearningSample:
        """Grade via the EXISTING EvaluationPolicyService; bind the level."""
        record = self._record(tenant_id, sample_id)
        if self._evaluation is None:
            raise LearningError("no evaluation seam composed; sample level cannot advance")
        evaluation = await self._evaluation.evaluate(
            tenant_id, record.sample.source_execution_id, output
        )
        level = getattr(evaluation, "level", None)
        if not isinstance(level, VerificationLevel):
            raise LearningError("evaluation seam returned no verification level")
        record.sample = record.sample.model_copy(update={"verification_level": level})
        return record.sample

    def set_verification_level(
        self, tenant_id: UUID, sample_id: UUID, level: VerificationLevel
    ) -> LearningSample:
        """Explicit reviewer act (e.g. human verification step, 22 §8)."""
        record = self._record(tenant_id, sample_id)
        record.sample = record.sample.model_copy(update={"verification_level": level})
        return record.sample

    # --- gates → GOLD → retrieval (the connection that was missing) -------------

    def admit_to_training(
        self,
        tenant_id: UUID,
        sample_id: UUID,
        signals: EligibilitySignals,
        *,
        dataset_id: UUID | None = None,
    ) -> LearningSample:
        """Run the EXISTING 22 §9 gate; persist the verdict on the sample."""
        record = self._record(tenant_id, sample_id)
        try:
            verdicts = self._eligibility.admit(record.sample, signals)
        except Exception:
            record.sample = record.sample.model_copy(
                update={"eligibility": LearningEligibility.INELIGIBLE}
            )
            record.eligibility_verdicts = self._eligibility.evaluate(record.sample, signals)
            raise
        record.eligibility_verdicts = verdicts
        record.sample = record.sample.model_copy(
            update={
                "eligibility": LearningEligibility.ELIGIBLE,
                "dataset_id": dataset_id if dataset_id is not None else uuid4(),
            }
        )
        return record.sample

    def promote_to_gold(
        self,
        tenant_id: UUID,
        sample_id: UUID,
        signals: PromotionSignals,
        *,
        actor_id: UUID | None = None,
        confidence: float = 0.9,
    ) -> MemoryItem:
        """Run the EXISTING 22 §11 gate; on pass: GOLD + audit + knowledge.

        Emits the 20 §9 ``TRAINING_DATASET_PROMOTED`` event (previously in
        the closed set but emitted nowhere) and writes the knowledge item
        through the EXISTING memory port — the retrieval substrate.
        """
        record = self._record(tenant_id, sample_id)
        if record.sample.eligibility is not LearningEligibility.ELIGIBLE:
            raise LearningError("sample must pass training eligibility before promotion (22 §8)")
        verdicts = self._promotion.admit(str(sample_id), signals)
        record.promotion_verdicts = verdicts
        record.sample = record.sample.model_copy(
            update={"verification_level": VerificationLevel.GOLD}
        )
        item = self._knowledge.upsert(
            MemoryItem(
                id=uuid4(),
                tenant_id=tenant_id,
                user_id=None,  # tenant-shared knowledge
                scope=MemoryScope.TENANT,
                key=record.knowledge_key,
                value=record.knowledge_value,
                source=GOLD_KNOWLEDGE_SOURCE,
                confidence=confidence,
                evidence_count=1,
                last_seen=utc_now(),
            )
        )
        if self._audit is not None:
            self._audit.append(
                AuditEvent(
                    tenant_id=tenant_id,
                    event_type=AuditEventType.TRAINING_DATASET_PROMOTED,
                    actor_id=actor_id,
                    details={
                        "sample_id": str(sample_id),
                        "knowledge_key": record.knowledge_key,
                        "memory_item_id": str(item.id),
                        "verdicts": dict(verdicts),
                    },
                )
            )
        return item

    # --- isolated learned-capability test path ----------------------------------

    def ask_learned(self, tenant_id: UUID, key: str) -> JsonObject:
        """Answer ONLY from GOLD knowledge — no production chat state touched.

        Deny-by-default: no GOLD item under the key = an explicit
        ``found: False`` answer; the service never fabricates content.
        """
        items = self._knowledge.query(tenant_id, scope=MemoryScope.TENANT, key=key)
        gold = [i for i in items if i.source == GOLD_KNOWLEDGE_SOURCE]
        if not gold:
            return {"found": False, "key": key, "answer": None, "evidence": None}
        best = max(gold, key=lambda i: i.confidence)
        return {
            "found": True,
            "key": key,
            "answer": best.value,
            "confidence": best.confidence,
            "evidence": {"memory_item_id": str(best.id), "source": best.source},
        }

    def learned_keys(self, tenant_id: UUID) -> tuple[str, ...]:
        """The tenant's GOLD knowledge keys — the testable surface, listed."""
        items = self._knowledge.query(tenant_id, scope=MemoryScope.TENANT)
        return tuple(sorted({i.key for i in items if i.source == GOLD_KNOWLEDGE_SOURCE}))

    # --- measurable capability re-test (R160) ------------------------------------
    #
    # Self-improvement must be MEASURED, not asserted: the same fixed probe
    # set is asked through the ISOLATED path before and after learning, and
    # the difference is reported as data — gained / lost / still-missing
    # keys. A "capability" here is exactly what the platform can already
    # prove: a GOLD answer exists for a key. Nothing is inferred from
    # model output; no probe passes without a GOLD item behind it.

    def capability_snapshot(self, tenant_id: UUID, probes: Sequence[str]) -> CapabilitySnapshot:
        """Ask every probe through ``ask_learned``; record found/missing."""
        ordered = tuple(dict.fromkeys(probes))  # dedupe, keep order
        found: list[str] = []
        missing: list[str] = []
        for key in ordered:
            (found if self.ask_learned(tenant_id, key)["found"] else missing).append(key)
        return CapabilitySnapshot(
            probes=ordered,
            found=tuple(found),
            missing=tuple(missing),
            taken_at=utc_now(),
        )

    @staticmethod
    def capability_delta(before: CapabilitySnapshot, after: CapabilitySnapshot) -> JsonObject:
        """before/after as DATA: gained, lost (regression), still missing."""
        if before.probes != after.probes:
            raise LearningError("capability delta requires the SAME probe set")
        b, a = set(before.found), set(after.found)
        gained = sorted(a - b)
        lost = sorted(b - a)
        return {
            "probes": len(after.probes),
            "before": {"found": len(before.found), "missing": len(before.missing)},
            "after": {"found": len(after.found), "missing": len(after.missing)},
            "gained": gained,
            "lost": lost,
            "still_missing": list(after.missing),
            "improved": bool(gained) and not lost,
            "regressed": bool(lost),
        }
