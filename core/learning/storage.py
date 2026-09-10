"""DEC03 B: explicit custody admission, never a learning/rights trust grant.

Only detached, bounded, scan-clean payloads can be offered to durable custody.
Quarantine retains counts/digests only. No default retention or tenant policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from core.contracts.base import JsonObject
from core.contracts.learning import LearningSample
from core.learning.errors import LearningError
from core.learning.gates import PROMOTION_CONDITIONS, TRAINING_ELIGIBILITY_CONDITIONS
from core.learning.sanitizer import sanitize_knowledge

MAX_CAPTURE_BYTES = 256 * 1024


class LearningStorageError(LearningError):
    """Safe, content-free refusal of durable learning custody."""


class LearningStorageConflict(LearningStorageError):
    """Idempotency/revision conflict; never overwrite the existing subject."""


@dataclass(frozen=True)
class RetentionPolicy:
    tenant_id: UUID
    policy_id: UUID
    retention_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, UUID) or not isinstance(self.policy_id, UUID):
            raise ValueError("storage policy requires UUID identities")
        if type(self.retention_seconds) is not int or self.retention_seconds <= 0:
            raise ValueError("retention_seconds must be an explicit positive integer")


@dataclass(frozen=True)
class PreparedCapture:
    content_digest: str
    payload: JsonObject | None
    quarantined: bool
    expires_at: datetime
    receipt: JsonObject


@dataclass(frozen=True)
class RecoveredCapture:
    """Detached custody data, never a new authorization or trust upgrade.

    Unavailable payloads are None, never empty clean dictionaries. The lifecycle
    must refuse payload-dependent operations when payload is None.
    """

    sample: LearningSample
    source_kind: str
    payload: JsonObject | None
    state: JsonObject
    revision: int
    expires_at: datetime
    content_digest: str


def validate_custody_state(state: object) -> JsonObject:
    """One closed metadata codec for writes and recovery; no raw snapshots."""
    allowed = {
        "version", "eligibility_verdicts", "promotion_verdicts", "evaluation_id", "memory_id",
    }
    if (
        not isinstance(state, dict)
        or set(state) - allowed
        or type(state.get("version")) is not int
        or state["version"] != 1
    ):
        raise LearningStorageError("unsupported custody state")
    for field, names in (
        ("eligibility_verdicts", TRAINING_ELIGIBILITY_CONDITIONS),
        ("promotion_verdicts", PROMOTION_CONDITIONS),
    ):
        verdicts = state.get(field, {})
        if (
            not isinstance(verdicts, dict)
            or set(verdicts) - set(names)
            or any(type(v) is not bool for v in verdicts.values())
        ):
            raise LearningStorageError("invalid custody verdicts")
    for field in ("evaluation_id", "memory_id"):
        value = state.get(field)
        if value is not None:
            try:
                if not isinstance(value, str) or str(UUID(value)) != value:
                    raise ValueError
            except ValueError:
                raise LearningStorageError("invalid custody reference") from None
    return deepcopy(state)


def custody_descriptor_digest(
    *, tenant_id: UUID, policy_id: UUID, rights_ref: UUID, retention_seconds: int,
    source_kind: str, source_execution_id: UUID, content_digest: str,
) -> str:
    """Exact retry descriptor, NOT a signature against database compromise."""
    return hashlib.sha256(json.dumps({
        "tenant": str(tenant_id), "policy": str(policy_id), "rights": str(rights_ref),
        "retention": retention_seconds, "source_kind": source_kind,
        "source": str(source_execution_id) if source_kind == "execution" else None,
        "content": content_digest,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def recover_capture(
    row: Mapping[str, object] | None,
    *, tenant_id: UUID, policy: RetentionPolicy | None, now: datetime,
) -> RecoveredCapture:
    """Validate a scoped repository row before exposing any content.

    No deletion, state transitions or trust grants happen here. Runtime must
    perform durable expiry/revocation and reconcile derived copies separately.
    Missing/changed policy and expiry suppress content even before that sweep.
    """
    if not isinstance(row, Mapping) or row.get("tenant_id") != tenant_id:
        raise LearningStorageError("unknown learning sample")
    try:
        return _recover_capture(row, tenant_id=tenant_id, policy=policy, now=now)
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError, LearningStorageError):
        # Contract/JSON validation can contain raw input in diagnostics. Suppress it.
        raise LearningStorageError("invalid custody record") from None


def _recover_capture(
    row: Mapping[str, object],
    *, tenant_id: UUID, policy: RetentionPolicy | None, now: datetime,
) -> RecoveredCapture:
    def identity(key: str) -> UUID:
        value = row[key]
        if not isinstance(value, UUID):
            raise ValueError
        return value

    sample_id, source_id = identity("sample_id"), identity("source_execution_id")
    policy_id, rights = identity("policy_id"), identity("rights_ref")
    identity("idempotency_key")
    retention = row["retention_seconds"]
    if type(retention) is not int:
        raise ValueError
    stored_policy = RetentionPolicy(tenant_id, policy_id, retention)
    revision = row["revision"]
    if type(revision) is not int or revision < 0:
        raise ValueError
    quarantined, revoked = row["quarantined"], row["revoked"]
    if type(quarantined) is not bool or type(revoked) is not bool:
        raise ValueError
    source_kind = row["source_kind"]
    if not isinstance(source_kind, str) or source_kind not in {"external", "execution"}:
        raise ValueError
    created, expires = row["created_at"], row["expires_at"]
    if (
        not isinstance(created, datetime) or created.utcoffset() is None
        or not isinstance(expires, datetime) or expires.utcoffset() is None
        or not isinstance(now, datetime) or now.utcoffset() is None
        or expires <= created or now < created
    ):
        raise ValueError
    # Repository creation can occur after preparation (especially execution-born
    # capture). A shorter remaining lifetime is safe; extending the policy is not.
    if expires > created + timedelta(seconds=stored_policy.retention_seconds):
        raise ValueError
    content_digest = row["content_digest"]
    if (
        not isinstance(content_digest, str) or len(content_digest) != 64
        or any(c not in "0123456789abcdef" for c in content_digest)
    ):
        raise ValueError
    if row["descriptor_digest"] != custody_descriptor_digest(
        tenant_id=tenant_id, policy_id=policy_id, rights_ref=rights,
        retention_seconds=stored_policy.retention_seconds, source_kind=source_kind,
        source_execution_id=source_id, content_digest=content_digest,
    ):
        raise ValueError
    state = validate_custody_state(row["state"])
    if row["dataset_id"] is not None:
        identity("dataset_id")
    sample = LearningSample.model_validate({
        "id": sample_id, "tenant_id": tenant_id, "source_execution_id": source_id,
        "eligibility": row["eligibility"], "sanitization_state": row["sanitization_state"],
        "verification_level": row["verification_level"], "dataset_id": row["dataset_id"],
    })
    payload = row["payload"]
    if quarantined or revoked:
        if payload is not None:
            raise ValueError
    elif payload is None:
        raise ValueError
    if payload is not None:
        if not isinstance(payload, dict) or set(payload) != {"knowledge_key", "knowledge_value"}:
            raise ValueError
        checked = prepare_capture(
            policy=stored_policy, tenant_id=tenant_id, policy_id=policy_id, rights_ref=rights,
            knowledge_key=payload["knowledge_key"], knowledge_value=payload["knowledge_value"],
            now=created,
        )
        if checked.quarantined or checked.content_digest != content_digest:
            raise ValueError
        payload = checked.payload
    if policy != stored_policy or now >= expires:
        payload = None
    return RecoveredCapture(
        sample=sample, source_kind=source_kind, payload=payload, state=state,
        revision=revision, expires_at=expires, content_digest=content_digest,
    )


def prepare_capture(
    *,
    policy: RetentionPolicy | None,
    tenant_id: UUID,
    policy_id: UUID | None,
    rights_ref: UUID | None,
    knowledge_key: str,
    knowledge_value: JsonObject,
    now: datetime,
) -> PreparedCapture:
    if policy is None or policy.tenant_id != tenant_id or policy.policy_id != policy_id:
        raise LearningStorageError("storage policy unavailable")
    if not isinstance(rights_ref, UUID):
        raise LearningStorageError("explicit rights attestation reference required")
    if now.utcoffset() is None:
        raise LearningStorageError("storage clock must be timezone aware")
    try:
        expires = now + timedelta(seconds=policy.retention_seconds)
    except (OverflowError, ValueError) as exc:
        raise LearningStorageError("retention cannot be represented") from exc
    if (
        not isinstance(knowledge_key, str)
        or not knowledge_key
        or not isinstance(knowledge_value, dict)
    ):
        raise LearningStorageError("invalid capture payload")
    try:
        canonical = json.dumps(
            {"key": knowledge_key, "value": knowledge_value},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise LearningStorageError("invalid capture JSON") from exc
    if len(canonical) > MAX_CAPTURE_BYTES:
        raise LearningStorageError("capture payload exceeds custody bound")
    decoded = json.loads(canonical)
    payload = {"knowledge_key": decoded["key"], "knowledge_value": decoded["value"]}
    scan = sanitize_knowledge(payload["knowledge_key"], payload["knowledge_value"])
    return PreparedCapture(
        content_digest=hashlib.sha256(canonical).hexdigest(),
        payload=payload if scan.clean else None,
        quarantined=not scan.clean,
        expires_at=expires,
        receipt={
            "scan_completed": True,
            "scan_clean": scan.clean,
            "finding_count": len(scan.findings),
            "scanned_paths": scan.scanned_paths,
            "verification_level": "RAW",
            "eligibility": "pending",
        },
    )
