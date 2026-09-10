"""DEC03 B: explicit custody admission, never a learning/rights trust grant.

Only detached, bounded, scan-clean payloads can be offered to durable custody.
Quarantine retains counts/digests only. No default retention or tenant policy.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from core.contracts.base import JsonObject
from core.learning.errors import LearningError
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
