"""DEC03 adapter acceptance; fake repository results are NOT live DB proof."""

import json
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from core.learning.storage import LearningStorageConflict, LearningStorageError, RetentionPolicy
from tests.learning.test_storage_policy_r178 import NOW, custody_row


def parse(env):
    from apps.composition.learning import learning_storage_policies_from_env

    return learning_storage_policies_from_env(env)


def entry(policy):
    return dict(
        tenant_id=str(policy.tenant_id),
        policy_id=str(policy.policy_id),
        retention_seconds=policy.retention_seconds,
    )


def test_config_no_ambient_or_default_policy(monkeypatch):
    _, policy = custody_row()
    monkeypatch.setenv("LEARNING_STORAGE_POLICIES", json.dumps([entry(policy)]))
    assert parse({}) == ()
    assert parse({"LEARNING_STORAGE_POLICIES": "[]"}) == ()


def test_config_preserves_explicit_tenant_identity_and_duration():
    _, first = custody_row()
    second = RetentionPolicy(uuid4(), first.policy_id, 73)
    assert parse({"LEARNING_STORAGE_POLICIES": json.dumps([entry(first), entry(second)])}) == (
        first,
        second,
    )


@pytest.mark.parametrize("raw", ["", " ", "null", "{}", "true", "[1]", "[{}]", "not-json"])
def test_config_refuses_malformed_values(raw):
    with pytest.raises(LearningStorageError, match="invalid learning storage policies"):
        parse({"LEARNING_STORAGE_POLICIES": raw})


@pytest.mark.parametrize(
    "field,value",
    [
        ("retention_seconds", True),
        ("retention_seconds", 0),
        ("retention_seconds", -1),
        ("retention_seconds", "3600"),
        ("retention_seconds", 1.5),
        ("tenant_id", "private-marker"),
        ("policy_id", None),
        ("raw-secret-field", "private-marker"),
    ],
)
def test_config_is_closed_strict_and_does_not_echo_input(field, value):
    _, policy = custody_row()
    data = entry(policy)
    data[field] = value
    with pytest.raises(LearningStorageError) as exc:
        parse({"LEARNING_STORAGE_POLICIES": json.dumps([data])})
    assert str(exc.value) == "invalid learning storage policies"
    assert exc.value.__suppress_context__


def test_config_rejects_duplicate_identities_and_json_fields():
    _, policy = custody_row()
    data = entry(policy)
    for raw in (
        json.dumps([data, data]),
        json.dumps([data]).replace(
            '"retention_seconds": 3600',
            '"retention_seconds": 1, "retention_seconds": 3600',
        ),
    ):
        with pytest.raises(LearningStorageError):
            parse({"LEARNING_STORAGE_POLICIES": raw})


class ObservedRepository:
    def __init__(self, row):
        self.row, self.calls, self.failure = deepcopy(row), [], None

    async def capture(self, **kwargs):
        self.calls.append(("capture", kwargs))
        if self.failure:
            raise self.failure
        return deepcopy(self.row)

    async def get(self, tenant_id, sample_id):
        self.calls.append(("get", tenant_id, sample_id))
        return deepcopy(self.row)

    async def list(self, tenant_id):
        self.calls.append(("list", tenant_id))
        return (deepcopy(self.row),)

    async def save(self, sample, state, *, expected_revision):
        self.calls.append(("save", sample, deepcopy(state), expected_revision))
        if self.failure:
            raise self.failure
        return expected_revision + 1


def adapter(repo, bridge, policies):
    from apps.composition.learning import DurableLearningCustody

    return DurableLearningCustody(
        repository=repo, bridge=bridge, policies=policies, clock=lambda: NOW
    )


def args(row):
    return dict(
        tenant_id=row["tenant_id"],
        actor_id=uuid4(),
        policy_id=row["policy_id"],
        rights_ref=row["rights_ref"],
        idempotency_key=row["idempotency_key"],
        knowledge_key="fact",
        knowledge_value={"nested": ["benign"]},
    )


@pytest.mark.parametrize(
    "missing", ["policy", "foreign_policy", "actor_id", "rights_ref", "idempotency_key"]
)
def test_admission_denies_before_any_io(missing):
    row, policy = custody_row()
    repo, request, policies = ObservedRepository(row), args(row), (policy,)
    if missing == "policy":
        policies = ()
    elif missing == "foreign_policy":
        policies = (RetentionPolicy(uuid4(), policy.policy_id, 3600),)
    else:
        request[missing] = None
    with AsyncBridge() as bridge:
        with pytest.raises(LearningStorageError):
            adapter(repo, bridge, policies).capture_external(**request)
    assert repo.calls == []


def test_capture_one_atomic_call_returns_stored_retry_identity():
    row, policy = custody_row()
    repo, request = ObservedRepository(row), args(row)
    with AsyncBridge() as bridge:
        restored = adapter(repo, bridge, (policy,)).capture_external(**request)
    assert restored.sample.id == row["sample_id"]
    assert restored.sample.source_execution_id == row["source_execution_id"]
    assert restored.sample.verification_level.value == "RAW"
    assert len(repo.calls) == 1 and repo.calls[0][0] == "capture"
    call = repo.calls[0][1]
    assert call["sample"].source_execution_id == call["execution"].id
    assert call["execution"].user_id == request["actor_id"]
    assert call["nodes"][0].input_ref["sample_id"] == str(call["sample"].id)
    assert call["nodes"][0].output_ref == call["prepared"].receipt
    assert call["nodes"][0].input_ref["content_sha256"] == call["prepared"].content_digest
    assert call["source_kind"] == "external"
    request["knowledge_value"]["nested"].append("changed")
    assert call["prepared"].payload["knowledge_value"] == {"nested": ["benign"]}


def test_secret_capture_offers_no_raw_content_to_repository():
    row, policy = custody_row()
    row.update(payload=None, quarantined=True)
    repo, request = ObservedRepository(row), args(row)
    marker = "ghp_" + "X" * 36
    request.update(knowledge_key=marker, knowledge_value={marker: marker})
    with AsyncBridge() as bridge:
        restored = adapter(repo, bridge, (policy,)).capture_external(**request)
    call = repo.calls[0][1]
    assert restored.payload is None
    assert call["prepared"].payload is None and call["prepared"].quarantined
    assert marker not in repr(call)


def test_write_failure_never_acknowledged_or_cached():
    row, policy = custody_row()
    repo = ObservedRepository(row)
    repo.failure = ConnectionError("database unavailable")
    with AsyncBridge() as bridge:
        with pytest.raises(ConnectionError):
            adapter(repo, bridge, (policy,)).capture_external(**args(row))
    assert [c[0] for c in repo.calls] == ["capture"]


@pytest.mark.parametrize(
    "mode", ["clean", "absent_policy", "changed_policy", "expired", "corrupt", "foreign"]
)
def test_reads_always_decode_without_caching_raw_rows(mode):
    row, policy = custody_row()
    policies = (policy,)
    if mode == "absent_policy":
        policies = ()
    elif mode == "changed_policy":
        policies = (RetentionPolicy(policy.tenant_id, policy.policy_id, 7200),)
    elif mode == "expired":
        row.update(created_at=NOW - timedelta(hours=1), expires_at=NOW)
    elif mode == "corrupt":
        row["state"] = {"version": 99}
    elif mode == "foreign":
        row["tenant_id"] = uuid4()
    repo = ObservedRepository(row)
    with AsyncBridge() as bridge:
        store = adapter(repo, bridge, policies)
        for read in (
            lambda: store.get(policy.tenant_id, row["sample_id"]),
            lambda: store.list(policy.tenant_id)[0],
        ):
            if mode in {"corrupt", "foreign"}:
                with pytest.raises(LearningStorageError):
                    read()
            else:
                assert (read().payload is not None) == (mode == "clean")
        repo.row["state"] = {"version": 99}
        with pytest.raises(LearningStorageError):
            store.get(policy.tenant_id, row["sample_id"])


@pytest.mark.parametrize("mode", ["clean", "stale", "missing_policy", "quarantined", "db_failure"])
def test_save_checks_current_policy_payload_and_revision(mode):
    from core.learning.storage import recover_capture

    row, policy = custody_row()
    sample = recover_capture(row, tenant_id=policy.tenant_id, policy=policy, now=NOW).sample
    policies = () if mode == "missing_policy" else (policy,)
    if mode == "quarantined":
        row.update(payload=None, quarantined=True)
    repo = ObservedRepository(row)
    if mode == "db_failure":
        repo.failure = LearningStorageConflict("concurrent write")
    with AsyncBridge() as bridge:
        store = adapter(repo, bridge, policies)
        kwargs = dict(expected_revision=1 if mode == "stale" else 0)
        if mode == "clean":
            assert store.save(sample, {"version": 1}, **kwargs) == 1
        else:
            with pytest.raises(LearningStorageError):
                store.save(sample, {"version": 1}, **kwargs)
    assert sum(c[0] == "save" for c in repo.calls) == (mode in {"clean", "db_failure"})
