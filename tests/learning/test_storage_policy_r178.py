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
