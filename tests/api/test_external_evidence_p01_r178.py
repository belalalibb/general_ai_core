"""P01 acceptance: real external subjects, shared evidence and failure containment."""

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
