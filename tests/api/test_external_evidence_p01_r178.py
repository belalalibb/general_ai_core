"""P01 acceptance: real external subjects, shared evidence and failure containment."""

import json
from uuid import UUID, uuid4

import httpx
import pytest

from apps.api.store import InMemoryExecutionStore
from core.contracts.execution import ExecutionNodeType
from tests.api.test_admin_api import World
from tests.api.test_promotion_evidence_r177 import SAMPLES, _app, _post, run


async def get(app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        return await c.get(path)


def capture(app, key="external.rule"):
    response = run(
        _post(
            app,
            SAMPLES,
            {
                "knowledge_key": key,
                "knowledge_value": {"answer": "bounded external fact"},
            },
        )
    )
    assert response.status_code == 201
    return response.json()


def test_capture_records_real_validator_subject_without_provider_inference():
    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)

    async def no_inference(request):
        pytest.fail("external ingestion must not invoke a model provider")

    world.adapter.generate = no_inference
    sample = capture(app)
    response = run(get(app, f"/v1/executions/{sample['source_execution_id']}"))
    assert response.status_code == 200
    report = store.get(world.principal.tenant_id, UUID(sample["source_execution_id"]))
    assert report.execution.user_id == world.principal.user_id
    assert report.nodes and all(
        node.node.type is ExecutionNodeType.VALIDATOR for node in report.nodes
    )
    assert all(not node.attempts for node in report.nodes)
    assert sample["verification_level"] == "RAW"
    assert sample["eligibility"] == sample["sanitization_state"] == "pending"


def test_external_evaluation_visible_in_shared_store_and_bound_to_exact_row():
    world = World()
    app = _app(world, strict=True)
    first, second = capture(app, "row.one"), capture(app, "row.two")
    assert first["source_execution_id"] != second["source_execution_id"]
    result = run(_post(app, f"{SAMPLES}/{first['id']}/evaluate", {"output": {"answer": "probe"}}))
    assert result.status_code == 200 and result.json()["evaluated"] is True
    listing = run(get(app, f"/v1/admin/executions/{first['source_execution_id']}/evaluations"))
    assert listing.status_code == 200 and len(listing.json()["evaluations"]) == 1
    record = listing.json()["evaluations"][0]
    assert record["execution_id"] == first["source_execution_id"]
    assert world.evaluations.get(world.principal.tenant_id, UUID(record["id"]))
    other = run(get(app, f"/v1/admin/executions/{second['source_execution_id']}/evaluations"))
    assert other.json()["evaluations"] == []


def test_subject_write_failure_never_acknowledges_sample():
    class Unavailable(InMemoryExecutionStore):
        def put(self, report):
            raise ConnectionError("subject persistence unavailable")

    world = World()
    app = _app(world, strict=True, store=Unavailable())
    with pytest.raises(ConnectionError):
        capture(app)
    assert app.state.learning_lifecycle_service.list_samples(world.principal.tenant_id) == ()


def test_evidence_write_failure_cannot_advance_verification():
    world = World()
    app = _app(world, strict=True)
    sample = capture(app)

    def refuse(record):
        raise ConnectionError("evidence persistence unavailable")

    world.evaluations.record = refuse
    with pytest.raises(ConnectionError):
        run(_post(app, f"{SAMPLES}/{sample['id']}/evaluate", {"output": {"answer": "probe"}}))
    stored = app.state.learning_lifecycle_service.get(world.principal.tenant_id, UUID(sample["id"]))
    assert stored.verification_level.value == "RAW"
    assert stored.eligibility.value == "pending"


def test_foreign_tenant_cannot_read_external_subject():
    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    sample = capture(app)
    store.get(world.principal.tenant_id, UUID(sample["source_execution_id"]))
    with pytest.raises(KeyError):
        store.get(uuid4(), UUID(sample["source_execution_id"]))


def test_flagged_batch_has_honest_secret_free_per_row_receipts():
    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    marker = "ghp_" + "X" * 36
    response = run(
        _post(
            app,
            "/v1/admin/learning/intake",
            {
                "format": "json",
                "content": json.dumps(
                    [{"key": "bad", "value": marker}, {"key": "good", "value": "fact"}]
                ),
                "expectations": {"required_columns": ["key", "value"], "key_column": "key"},
            },
        )
    )
    assert response.status_code == 201
    assert response.json()["flagged"] == 1
    lifecycle = app.state.learning_lifecycle_service
    samples = lifecycle.list_samples(world.principal.tenant_id)
    assert len(samples) == 2
    assert len({s.source_execution_id for s in samples}) == 2
    receipts = [store.get(world.principal.tenant_id, s.source_execution_id) for s in samples]
    for sample, receipt in zip(samples, receipts, strict=True):
        node = receipt.nodes[0].node
        assert node.input_ref["sample_id"] == str(sample.id)
        assert node.output_ref["scan_completed"] is True
        assert sample.verification_level.value == "RAW"
        assert sample.eligibility.value == "pending"
        assert marker not in node.model_dump_json()
        assert "value" not in node.input_ref and "findings" not in node.output_ref
    assert receipts[0].nodes[0].node.output_ref["scan_clean"] is False
    assert receipts[1].nodes[0].node.output_ref["scan_clean"] is True
    refusal = run(_post(app, f"{SAMPLES}/{samples[0].id}/sanitize", {"passed": True}))
    assert refusal.status_code == 200 and refusal.json()["sanitized"] is False


def test_quarantined_batch_creates_no_ingestion_subjects():
    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    response = run(
        _post(
            app,
            "/v1/admin/learning/intake",
            {
                "format": "json",
                "content": "not json",
                "expectations": {"required_columns": ["key"], "key_column": "key"},
            },
        )
    )
    assert response.status_code == 422
    assert store.list(world.principal.tenant_id) == ()
    assert app.state.learning_lifecycle_service.list_samples(world.principal.tenant_id) == ()


def test_composed_direct_capture_cannot_borrow_foreign_demo_actor():
    from core.learning.errors import LearningError

    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    with pytest.raises(LearningError, match="admitted actor"):
        app.state.learning_lifecycle_service.capture_external(
            uuid4(), knowledge_key="foreign", knowledge_value={"fact": "x"}
        )
    assert store.list(world.principal.tenant_id) == ()


def test_authenticated_capture_records_resolved_actor_not_demo_identity():
    from tests.api.test_self_evolution_r161 import _admin, _profile

    profile = _profile()
    headers, tenant = _admin(profile)

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
        ) as client:
            return await client.post(
                SAMPLES,
                headers=headers,
                json={
                    "knowledge_key": "authenticated",
                    "knowledge_value": {"fact": "x"},
                },
            )

    response = run(request())
    assert response.status_code == 201
    session = profile.identity.resolve_session(headers["Authorization"].split(" ", 1)[1])
    receipt = profile.app.state.scenario_service.execution_store.get(
        tenant, UUID(response.json()["source_execution_id"])
    )
    assert receipt.execution.user_id == session.user_id
    assert receipt.execution.tenant_id == session.tenant_id


def test_caller_mutation_cannot_change_admitted_content_under_existing_receipt():
    world = World()
    app = _app(world, strict=True)
    service = app.state.learning_lifecycle_service
    payload = {"nested": {"answer": "original"}}
    first = service.capture_external(
        world.principal.tenant_id, knowledge_key="stable", knowledge_value=payload
    )
    payload["nested"]["answer"] = "changed"
    service.capture_external(
        world.principal.tenant_id,
        knowledge_key="stable",
        knowledge_value={"nested": {"answer": "original"}},
    )
    assert service.derived_signals(world.principal.tenant_id, first.id)["deduplicated"] is False


def test_validator_receipt_reconstruction_does_not_invent_provider_response():
    from apps.composition.durability import report_from_record
    from infrastructure.db.repositories.executions import ExecutionRecord

    world = World()
    store = InMemoryExecutionStore()
    app = _app(world, strict=True, store=store)
    sample = capture(app)
    original = store.get(world.principal.tenant_id, UUID(sample["source_execution_id"]))
    recovered = report_from_record(
        ExecutionRecord(execution=original.execution, nodes=tuple(n.node for n in original.nodes))
    )
    assert recovered.nodes[0].response is None
    assert recovered.nodes[0].node == original.nodes[0].node
    assert recovered.final_output == original.final_output


@pytest.mark.parametrize("secret_location", [None, "key", "field", "value"])
def test_receipt_builder_is_write_free_and_content_safe(secret_location, monkeypatch):
    import hashlib

    from apps.api import ingestion
    from core.contracts.execute import ExecutionStatus

    marker = "ghp_" + "X" * 36
    key = marker if secret_location == "key" else "fact"
    field = marker if secret_location == "field" else "answer"
    value = {field: marker if secret_location == "value" else "bounded fact"}
    tenant, actor, sample = uuid4(), uuid4(), uuid4()
    scans = []
    scan = ingestion.sanitize_knowledge

    def observed_scan(knowledge_key, knowledge_value):
        scans.append((knowledge_key, knowledge_value))
        return scan(knowledge_key, knowledge_value)

    def refuse_write(*args):
        pytest.fail("building a receipt must not write an execution")

    monkeypatch.setattr(ingestion, "sanitize_knowledge", observed_scan)
    monkeypatch.setattr(InMemoryExecutionStore, "put", refuse_write)
    report = ingestion.build_external_ingestion_report(tenant, sample, actor, key, value)
    digest = hashlib.sha256(
        json.dumps({"key": key, "value": value}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert scans == [(key, value)]
    assert report.execution.tenant_id == tenant and report.execution.user_id == actor
    assert report.execution.request_hash == "sha256:" + digest
    assert report.execution.status is ExecutionStatus.SUCCEEDED
    assert report.execution.completed_at >= report.execution.created_at
    assert len(report.nodes) == 1
    node = report.nodes[0]
    assert node.attempts == () and node.response is None
    assert node.node.type is ExecutionNodeType.VALIDATOR
    assert node.node.execution_id == report.execution.id
    assert node.node.input_ref["sample_id"] == str(sample)
    assert node.node.input_ref["content_sha256"] == digest
    assert node.node.output_ref["scan_clean"] is (secret_location is None)
    assert node.node.output_ref["verification_level"] == "RAW"
    assert node.node.output_ref["eligibility"] == "pending"
    encoded = report.execution.model_dump_json() + node.node.model_dump_json()
    assert marker not in encoded and "bounded fact" not in encoded
    assert "findings" not in node.node.output_ref
    value[field] = "changed after construction"
    assert report.execution.model_dump_json() + node.node.model_dump_json() == encoded


def test_receipt_builder_requires_actor_before_scanning(monkeypatch):
    from apps.api import ingestion
    from core.learning.errors import LearningError

    def refuse_scan(*args):
        pytest.fail("missing actor must refuse before inspecting content")

    monkeypatch.setattr(ingestion, "sanitize_knowledge", refuse_scan)
    with pytest.raises(LearningError, match="admitted actor"):
        ingestion.build_external_ingestion_report(uuid4(), uuid4(), None, "fact", {})


def test_receipt_builder_scan_failure_cannot_manufacture_completion(monkeypatch):
    from apps.api import ingestion

    def broken_scan(*args):
        raise RuntimeError("scan unavailable")

    monkeypatch.setattr(ingestion, "sanitize_knowledge", broken_scan)
    with pytest.raises(RuntimeError, match="scan unavailable"):
        ingestion.build_external_ingestion_report(uuid4(), uuid4(), uuid4(), "fact", {})


def test_legacy_recorder_delegates_to_builder_and_writes_exactly_once(monkeypatch):
    from apps.api import ingestion

    tenant, actor, sample = uuid4(), uuid4(), uuid4()
    report = ingestion.build_external_ingestion_report(tenant, sample, actor, "fact", {})
    calls, writes = [], []

    def build(*args):
        calls.append(args)
        return report

    class ObservedStore(InMemoryExecutionStore):
        def put(self, candidate):
            writes.append(candidate)
            super().put(candidate)

    monkeypatch.setattr(ingestion, "build_external_ingestion_report", build)
    store = ObservedStore()
    recorder = ingestion.ExternalIngestionRecorder(store, default_actor=(tenant, actor))
    execution_id = recorder.record(tenant, sample, None, "fact", {})
    assert calls == [(tenant, sample, actor, "fact", {})]
    assert writes == [report]
    assert execution_id == report.execution.id
    assert store.get(tenant, execution_id) is report


def governed_app(world, custody, *, store=None):
    """Exercise create_app injection, never post-construction rewiring."""
    from dataclasses import replace

    from apps.api.app import create_app
    from core.execution.service import ExecutionService
    from core.memory.memory import InMemoryMemoryStore

    return create_app(
        router=world.router,
        execution_service=ExecutionService(
            adapters={}, credential_refs={}, bindings=world.bindings, usage=world.usage
        ),
        principal=world.principal,
        admin=replace(world.surface(), audit=world.audit),
        memory=InMemoryMemoryStore(), store=store,
        learning_custody=custody, strict_promotion_evidence=True,
    )


def custody_api_world():
    from dataclasses import replace

    from tests.learning.test_learning_lifecycle_e2e import _Custody

    custody = _Custody()
    world = World()
    world.principal = replace(world.principal, tenant_id=custody.current.sample.tenant_id)
    return world, custody


def custody_body():
    return dict(
        knowledge_key="fact", knowledge_value={"answer": "fact"},
        policy_id=str(uuid4()), rights_ref=str(uuid4()), idempotency_key=str(uuid4()),
    )


def test_governed_api_forwards_refs_and_authenticated_actor_without_shadow():
    world, custody = custody_api_world()
    app = governed_app(world, custody)
    body = custody_body()
    response = run(_post(app, SAMPLES, body))
    assert response.status_code == 201
    assert response.json()["id"] == str(custody.current.sample.id)
    forwarded = custody.calls[0][-1]
    assert forwarded["actor_id"] == world.principal.user_id
    for name in ("policy_id", "rights_ref", "idempotency_key"):
        assert forwarded[name] == UUID(body[name])
    assert app.state.learning_lifecycle_service._samples == {}
    restored = run(get(governed_app(world, custody), f"{SAMPLES}/{response.json()['id']}"))
    assert restored.status_code == 200
    assert restored.json()["sample"] == response.json()


@pytest.mark.parametrize("missing", ["policy_id", "rights_ref", "idempotency_key"])
def test_governed_api_missing_refs_refuse_before_capture(missing):
    world, custody = custody_api_world()
    body = custody_body()
    del body[missing]
    response = run(_post(governed_app(world, custody), SAMPLES, body))
    assert response.status_code == 422
    assert custody.calls == []


def test_governed_api_nonadmin_actor_cannot_use_source_provenance():
    from dataclasses import replace

    world, custody = custody_api_world()
    world.principal = replace(world.principal, is_admin=False)
    body = custody_body()
    body["source_execution_id"] = str(custody.current.sample.source_execution_id)
    response = run(_post(governed_app(world, custody), SAMPLES, body))
    assert response.status_code == 403
    assert custody.calls == []


@pytest.mark.parametrize("operation", ["capture", "read", "evaluate", "sanitize"])
@pytest.mark.parametrize("conflict", [False, True])
def test_governed_api_storage_refusals_are_constant_and_secret_safe(operation, conflict):
    from core.learning.storage import LearningStorageConflict, LearningStorageError

    world, custody = custody_api_world()
    marker = "untrusted-backend-detail"

    def refuse(*args, **kwargs):
        raise (LearningStorageConflict if conflict else LearningStorageError)(marker)

    custody.capture_external = refuse
    custody.get = refuse
    app = governed_app(world, custody)
    path = f"{SAMPLES}/{custody.current.sample.id}"
    if operation == "capture":
        response = run(_post(app, SAMPLES, custody_body()))
    elif operation == "read":
        response = run(get(app, path))
    else:
        body = {"output": {"answer": "fact"}} if operation == "evaluate" else {"passed": True}
        response = run(_post(app, f"{path}/{operation}", body))
    assert response.status_code == (409 if conflict else 404)
    assert marker not in response.text
    assert response.json()["error"]["message"] == "Learning storage unavailable."


def test_governed_intake_retry_refs_and_metadata_only_quarantine():
    from dataclasses import replace
    from uuid import uuid5

    world, custody = custody_api_world()
    custody.current = replace(custody.current, payload=None)
    app = governed_app(world, custody)
    body = custody_body()
    del body["knowledge_key"], body["knowledge_value"]
    batch_id = UUID(body["idempotency_key"])
    marker = "ghp_" + "X" * 36
    body.update(
        format="json", content=json.dumps([{"key": marker, marker: "x"}]),
        expectations={"required_columns": ["key", marker], "key_column": "key"},
    )
    for _ in range(2):
        response = run(_post(app, "/v1/admin/learning/intake", body))
        assert response.status_code == 201
        assert marker not in response.text
        row = response.json()["admitted"][0]
        assert row["knowledge_key"] is None and row["findings"] == []
        assert row["scan_clean"] is False
        assert response.json()["columns_seen"] == []
    calls = [c[-1] for c in custody.calls if c[0] == "external"]
    assert len(calls) == 2
    assert all(c["idempotency_key"] == uuid5(batch_id, "row:1") for c in calls)
    assert all(c["actor_id"] == world.principal.user_id for c in calls)


def test_governed_intake_parse_refusal_does_not_echo_secret_field():
    world, custody = custody_api_world()
    marker = "ghp_" + "X" * 36
    body = custody_body()
    del body["knowledge_key"], body["knowledge_value"]
    body.update(
        format="json", content=json.dumps([{marker: {"nested": "x"}}]),
        expectations={"required_columns": ["key"], "key_column": "key"},
    )
    response = run(_post(governed_app(world, custody), "/v1/admin/learning/intake", body))
    assert response.status_code == 422
    assert marker not in response.text
    assert custody.calls == []


# --- DEC03 operator governance: revoke / retention sweep + reconcile / legacy release


class _GovernedCustody:
    """Port double recording governance acts; no database claims."""

    def __init__(self, inner):
        self.inner = inner
        self.acts = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def revoke_policy(self, tenant_id, policy_id):
        self.acts.append(("revoke", tenant_id, policy_id))
        return 1

    def expire(self, tenant_id, now):
        self.acts.append(("expire", tenant_id, now))
        return 2

    def release_legacy_hold(self, tenant_id, *, reconciliation_ref):
        self.acts.append(("release", tenant_id, reconciliation_ref))
        return True


GOVERN = "/v1/admin/learning/custody"


def governed_world():
    world, custody = custody_api_world()
    governed = _GovernedCustody(custody)
    return world, governed, governed_app(world, governed)


def test_governance_revoke_requires_admin_and_is_audited():
    from core.contracts.audit import AuditEventType

    world, custody, app = governed_world()
    tenant = world.principal.tenant_id
    policy = uuid4()
    response = run(_post(app, f"{GOVERN}/revoke", {"policy_id": str(policy)}))
    assert response.status_code == 200
    assert response.json() == {"policy_id": str(policy), "revoked_samples": 1}
    assert custody.acts == [("revoke", tenant, policy)]
    events = world.audit.read(tenant, event_type=AuditEventType.SECURITY_POLICY_CHANGED)
    assert len(events) == 1 and events[0].actor_id == world.principal.user_id
    assert events[0].details["act"] == "learning_policy_revoked"
    assert events[0].details["policy_id"] == str(policy)


def test_governance_retention_sweep_uses_server_clock_and_reconciles_copies():
    world, custody, app = governed_world()
    response = run(_post(app, f"{GOVERN}/sweep", {}))
    assert response.status_code == 200
    assert response.json() == {
        "expired_samples": 2,
        "derived_copies": {"checked": 0, "removed": 0, "retained": 0},
    }
    act = custody.acts[0]
    assert act[0] == "expire" and act[1] == world.principal.tenant_id
    assert act[2].utcoffset() is not None  # server clock, never caller-supplied


def test_governance_legacy_release_requires_explicit_reconciliation_reference():
    from core.contracts.audit import AuditEventType

    world, custody, app = governed_world()
    assert run(_post(app, f"{GOVERN}/release-legacy-hold", {})).status_code == 422
    ref = uuid4()
    released = run(_post(app, f"{GOVERN}/release-legacy-hold", {"reconciliation_ref": str(ref)}))
    assert released.status_code == 200
    assert released.json() == {"released": True, "reconciliation_ref": str(ref)}
    assert custody.acts == [("release", world.principal.tenant_id, ref)]
    events = world.audit.read(
        world.principal.tenant_id, event_type=AuditEventType.SECURITY_POLICY_CHANGED
    )
    assert events[0].details["act"] == "learning_legacy_hold_released"
    assert events[0].details["reconciliation_ref"] == str(ref)


def test_governance_routes_absent_without_custody_and_denied_to_non_admin():
    from dataclasses import replace

    world, custody = custody_api_world()
    assert run(_post(_app(world, strict=True), f"{GOVERN}/sweep", {})).status_code == 404
    world.principal = replace(world.principal, is_admin=False)
    app = governed_app(world, _GovernedCustody(custody))
    assert run(_post(app, f"{GOVERN}/sweep", {})).status_code == 403
    assert run(_post(app, f"{GOVERN}/revoke", {"policy_id": str(uuid4())})).status_code == 403


# --- DEC03 partial batch: rows are independent atomic captures with stable retry keys


class _FailingRowCustody:
    """Port double: the Nth external capture fails after earlier rows committed."""

    def __init__(self, inner, *, fail_on_call):
        self.inner = inner
        self.fail_on_call = fail_on_call
        self.keys = []

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def capture_external(self, tenant_id, **kwargs):
        from core.learning.storage import LearningStorageError

        self.keys.append(kwargs["idempotency_key"])
        if len(self.keys) == self.fail_on_call:
            raise LearningStorageError("row custody unavailable")
        return self.inner.capture_external(tenant_id, **kwargs)


def intake_body(rows, batch_key):
    body = custody_body()
    del body["knowledge_key"], body["knowledge_value"]
    body["idempotency_key"] = str(batch_key)
    body.update(
        format="json", content=json.dumps(rows),
        expectations={"required_columns": ["key", "value"], "key_column": "key"},
    )
    return body


def test_governed_intake_later_row_failure_keeps_earlier_rows_and_retry_keys_stable():
    from uuid import uuid5

    world, inner = custody_api_world()
    custody = _FailingRowCustody(inner, fail_on_call=2)
    app = governed_app(world, custody)
    batch = uuid4()
    rows = [{"key": "one", "value": "a"}, {"key": "two", "value": "b"}]
    failed = run(_post(app, "/v1/admin/learning/intake", intake_body(rows, batch)))
    # The batch is NOT all-or-nothing: row 1 committed before row 2 refused.
    assert failed.status_code == 404
    assert failed.json()["error"]["message"] == "Learning storage unavailable."
    assert "row custody unavailable" not in failed.text
    committed = [c[-1]["idempotency_key"] for c in inner.calls if c[0] == "external"]
    assert committed == [uuid5(batch, "row:1")]
    assert custody.keys == [uuid5(batch, "row:1"), uuid5(batch, "row:2")]
    # Same batch key replays: row 1 reuses ITS key (custody dedups), row 2 proceeds.
    retried = run(_post(app, "/v1/admin/learning/intake", intake_body(rows, batch)))
    assert retried.status_code == 201
    assert [r["row"] for r in retried.json()["admitted"]] == [1, 2]
    assert custody.keys[2:] == [uuid5(batch, "row:1"), uuid5(batch, "row:2")]
    assert app.state.learning_lifecycle_service._samples == {}


def test_governed_intake_row_keys_are_batch_scoped_and_order_stable():
    from uuid import uuid5

    world, inner = custody_api_world()
    app = governed_app(world, inner)
    rows = [
        {"key": "one", "value": "a"}, {"key": "", "value": "refused"}, {"key": "3", "value": "c"}
    ]
    first, second = uuid4(), uuid4()
    for batch in (first, second):
        response = run(_post(app, "/v1/admin/learning/intake", intake_body(rows, batch)))
        assert response.status_code == 201
        assert [r["row"] for r in response.json()["refused"]] == [2]
        assert [r["row"] for r in response.json()["admitted"]] == [1, 3]
    keys = [c[-1]["idempotency_key"] for c in inner.calls if c[0] == "external"]
    # Refused row 2 consumed no custody key; row numbers, not positions, derive keys.
    assert keys == [uuid5(first, "row:1"), uuid5(first, "row:3"),
                    uuid5(second, "row:1"), uuid5(second, "row:3")]
    assert len(set(keys)) == 4
