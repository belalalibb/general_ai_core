"""DEC03 B failing-first: policy and custody do not confer learning trust."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def prepare(value=None, **overrides):
    from core.learning.storage import RetentionPolicy, prepare_capture

    tenant, policy_id = uuid4(), uuid4()
    args = dict(
        policy=RetentionPolicy(tenant, policy_id, 3600),
        tenant_id=tenant,
        policy_id=policy_id,
        rights_ref=uuid4(),
        knowledge_key="fact",
        knowledge_value={"answer": "benign"} if value is None else value,
        now=NOW,
    )
    args.update(overrides)
    return prepare_capture(**args)


def test_absent_policy_denies_before_retaining_any_payload():
    from core.learning.storage import LearningStorageError

    with pytest.raises(LearningStorageError, match="policy"):
        prepare(policy=None)


def test_foreign_policy_and_missing_rights_reference_deny():
    from core.learning.storage import LearningStorageError

    for kwargs in ({"tenant_id": uuid4()}, {"policy_id": uuid4()}, {"rights_ref": None}):
        with pytest.raises(LearningStorageError):
            prepare(**kwargs)


@pytest.mark.parametrize("seconds", [None, 0, -1, True, 1.5, float("inf")])
def test_retention_must_be_explicit_positive_integer(seconds):
    from core.learning.storage import RetentionPolicy

    with pytest.raises(ValueError):
        RetentionPolicy(uuid4(), uuid4(), seconds)


def test_clean_payload_has_explicit_expiry_but_no_trust_grant():
    prepared = prepare()
    assert prepared.expires_at == NOW + timedelta(hours=1)
    assert prepared.quarantined is False
    assert prepared.payload == {"knowledge_key": "fact", "knowledge_value": {"answer": "benign"}}
    assert prepared.receipt["verification_level"] == "RAW"
    assert prepared.receipt["eligibility"] == "pending"
    assert "benign" not in json.dumps(prepared.receipt)


def test_secret_in_value_or_key_is_metadata_only_quarantine():
    marker = "ghp_" + "Z" * 36
    for value in ({"answer": marker}, {marker: "value"}, {"password": "private"}):
        prepared = prepare(value)
        assert prepared.quarantined is True
        assert prepared.payload is None
        encoded = json.dumps(prepared.receipt)
        assert marker not in encoded and "private" not in encoded
        assert "findings" not in prepared.receipt
        assert prepared.receipt["scan_clean"] is False


def test_knowledge_key_secret_is_also_quarantined():
    prepared = prepare(knowledge_key="ghp_" + "X" * 36)
    assert prepared.quarantined and prepared.payload is None


def test_payload_is_detached_and_digest_changes_with_content():
    value = {"nested": ["original"]}
    prepared = prepare(value)
    value["nested"][0] = "changed"
    assert prepared.payload["knowledge_value"]["nested"] == ["original"]
    assert prepared.content_digest != prepare(value).content_digest


def test_nonfinite_or_oversized_content_is_refused():
    from core.learning.storage import LearningStorageError

    for value in ({"n": float("nan")}, {"value": "x" * (256 * 1024)}):
        with pytest.raises(LearningStorageError):
            prepare(value)


def custody_row():
    """Repository-shaped fixture with independently computed descriptor."""
    import hashlib

    from core.learning.storage import RetentionPolicy, prepare_capture

    tenant, policy_id, rights = uuid4(), uuid4(), uuid4()
    policy = RetentionPolicy(tenant, policy_id, 3600)
    prepared = prepare_capture(
        policy=policy, tenant_id=tenant, policy_id=policy_id, rights_ref=rights,
        knowledge_key="fact", knowledge_value={"nested": ["benign"]}, now=NOW,
    )
    row = dict(
        sample_id=uuid4(), tenant_id=tenant, source_execution_id=uuid4(),
        idempotency_key=uuid4(), policy_id=policy_id, rights_ref=rights,
        retention_seconds=3600, created_at=NOW, expires_at=prepared.expires_at,
        content_digest=prepared.content_digest, source_kind="external",
        payload=prepared.payload, quarantined=False, revoked=False, revision=0,
        state={"version": 1}, eligibility="pending", sanitization_state="pending",
        verification_level="RAW", dataset_id=None,
    )
    row["descriptor_digest"] = hashlib.sha256(json.dumps({
        "tenant": str(tenant), "policy": str(policy_id), "rights": str(rights),
        "retention": 3600, "source_kind": "external", "source": None,
        "content": prepared.content_digest,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return row, policy


def recover(row, policy, **kwargs):
    from core.learning.storage import recover_capture

    args = dict(tenant_id=policy.tenant_id, policy=policy, now=NOW)
    args.update(kwargs)
    return recover_capture(row, **args)


def test_recovery_roundtrip_preserves_raw_state_and_detaches_content():
    row, policy = custody_row()
    restored = recover(row, policy)
    assert restored.sample.id == row["sample_id"]
    assert restored.sample.source_execution_id == row["source_execution_id"]
    assert restored.sample.verification_level.value == "RAW"
    assert restored.sample.eligibility.value == "pending"
    assert restored.revision == 0 and restored.source_kind == "external"
    row["payload"]["knowledge_value"]["nested"].append("caller mutation")
    row["state"]["version"] = 2
    assert restored.payload["knowledge_value"]["nested"] == ["benign"]
    assert restored.state == {"version": 1}


@pytest.mark.parametrize("field,value", [
    ("state", {"version": 2}), ("state", {"version": True}),
    ("state", {"version": 1, "raw_findings": ["private"]}),
    ("state", {"version": 1, "eligibility_verdicts": {"unknown": True}}),
    ("state", {"version": 1, "evaluation_id": "not-a-uuid"}),
    ("state", {"version": 1, "eligibility_verdicts": {"deduplicated": 1}}),
    ("revision", True), ("revision", -1), ("revision", "1"),
    ("quarantined", 0), ("revoked", "false"),
    ("source_kind", "invented"), ("content_digest", "0" * 64),
    ("descriptor_digest", "0" * 64), ("retention_seconds", True),
    ("expires_at", NOW), ("created_at", NOW.replace(tzinfo=None)),
    ("expires_at", NOW + timedelta(hours=2)), ("sample_id", "not-a-uuid"),
    ("rights_ref", None), ("eligibility", "invented"),
    ("verification_level", "invented"), ("payload", {}),
    ("payload", {"knowledge_key": "fact", "knowledge_value": {}, "extra": "private"}),
])
def test_recovery_refuses_malformed_record_without_echoing_content(field, value):
    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    row[field] = value
    with pytest.raises(LearningStorageError) as exc:
        recover(row, policy)
    assert "private" not in str(exc.value) and "benign" not in str(exc.value)


def test_recovery_missing_and_foreign_tenant_are_indistinguishable():
    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    messages = []
    for data in (None, {**row, "tenant_id": uuid4()}):
        with pytest.raises(LearningStorageError) as exc:
            recover(data, policy)
        messages.append(str(exc.value))
    assert messages[0] == messages[1] == "unknown learning sample"


@pytest.mark.parametrize("reason", ["expired", "policy_absent", "policy_changed", "policy_foreign"])
def test_recovery_unavailable_content_is_never_an_empty_clean_payload(reason):
    from core.learning.storage import RetentionPolicy, recover_capture

    row, policy = custody_row()
    active, now = policy, NOW
    if reason == "expired":
        now = row["expires_at"]
    elif reason == "policy_absent":
        active = None
    elif reason == "policy_changed":
        active = RetentionPolicy(policy.tenant_id, policy.policy_id, 7200)
    else:
        active = RetentionPolicy(uuid4(), policy.policy_id, 3600)
    restored = recover_capture(row, tenant_id=policy.tenant_id, policy=active, now=now)
    assert restored.payload is None
    assert restored.sample.id == row["sample_id"]
    assert restored.sample.eligibility.value == "pending"  # no invented evidence


@pytest.mark.parametrize("flag", ["quarantined", "revoked"])
def test_recovery_redacted_lineage_survives_without_rescanning_empty_content(flag):
    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    row[flag] = True
    with pytest.raises(LearningStorageError):
        recover(row, policy)  # invalid raw payload on a redacted row
    row["payload"] = None
    restored = recover(row, policy)
    assert restored.payload is None
    assert restored.sample.source_execution_id == row["source_execution_id"]


def test_recovery_unexplained_payload_loss_refuses_instead_of_manufacturing_clean_data():
    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    row["payload"] = None
    with pytest.raises(LearningStorageError):
        recover(row, policy)


def test_recovery_rescans_secret_payload_even_with_matching_content_digest():
    import hashlib

    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    row["payload"]["knowledge_value"] = {"password": "private-marker"}
    row["content_digest"] = hashlib.sha256(json.dumps({
        "key": "fact", "value": row["payload"]["knowledge_value"],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    row["descriptor_digest"] = hashlib.sha256(json.dumps({
        "tenant": str(policy.tenant_id), "policy": str(policy.policy_id),
        "rights": str(row["rights_ref"]), "retention": 3600,
        "source_kind": "external", "source": None, "content": row["content_digest"],
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(LearningStorageError) as exc:
        recover(row, policy)
    assert "private-marker" not in str(exc.value)


@pytest.mark.parametrize("now", [NOW.replace(tzinfo=None), NOW - timedelta(seconds=1)])
def test_recovery_requires_aware_non_backward_clock(now):
    from core.learning.storage import LearningStorageError

    row, policy = custody_row()
    with pytest.raises(LearningStorageError):
        recover(row, policy, now=now)
