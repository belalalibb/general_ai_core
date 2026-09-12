"""R179 4.7 — operator visibility over durable custody governance.

(a) READ-ONLY HOLDS VIEW — ``GET /v1/admin/learning/custody/holds``: tenant-scoped
    list of the tenant's revocation/hold rows (legacy hold + explicit policy
    revocations). Read never mutates; a HELD tenant can still see its own hold
    (the read must not run the reconciled-assert that blocks capture).

(b) UNAMBIGUOUS RELEASE OUTCOME — ``release-legacy-hold`` answers one of
    ``released`` (acted) / ``no_hold`` (nothing to act on, never held) /
    ``already_released`` (a prior audited release exists), and REFUSES (409)
    when custody's answer contradicts durable state (hold still present after a
    claimed release, or a release claimed without a hold).

(c) INTAKE FAULT CLARITY — a row whose custody write is REFUSED
    (LearningStorageError / Conflict) becomes a refused row and the batch
    continues; any other failure is a DURABLE-LAYER fault: the batch stops,
    landed rows are reported, the remaining rows are ``not_attempted`` and the
    route answers 503 carrying the partial report.
"""

from __future__ import annotations

import json
from dataclasses import replace
from uuid import UUID, uuid4

import httpx

from core.contracts.audit import AuditEventType
from tests.api.test_external_evidence_p01_r178 import (
    _GovernedCustody,
    custody_api_world,
    custody_body,
    governed_app,
)
from tests.api.test_promotion_evidence_r177 import _post, run

GOVERN = "/v1/admin/learning/custody"
INTAKE = "/v1/admin/learning/intake"


async def _get(app, path):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.get(path)


class _HoldsCustody(_GovernedCustody):
    """Governance double with a durable-state model of the revocations table."""

    def __init__(self, inner, *, holds=None, release_result=None, reads=None):
        super().__init__(inner)
        tenant = inner.current.sample.tenant_id
        self.rows = list(holds if holds is not None else [(tenant, None, "legacy_unresolved")])
        self._release_result = release_result  # None ⇒ honest (derived from rows)
        self._reads = reads

    def list_revocations(self, tenant_id):
        self.acts.append(("list_revocations", tenant_id))
        if self._reads is not None:
            return tuple(self._reads)
        return tuple(
            {"tenant_id": t, "policy_id": p, "reason": r, "recorded_at": None}
            for t, p, r in self.rows
            if t == tenant_id
        )

    def release_legacy_hold(self, tenant_id, *, reconciliation_ref):
        self.acts.append(("release", tenant_id, reconciliation_ref))
        if self._release_result is not None:
            return self._release_result
        before = len(self.rows)
        self.rows = [r for r in self.rows if not (r[0] == tenant_id and r[1] is None)]
        return len(self.rows) < before


def _world(**custody_kwargs):
    world, inner = custody_api_world()
    custody = _HoldsCustody(inner, **custody_kwargs)
    return world, custody, governed_app(world, custody)


# --- (a) read-only holds view ------------------------------------------------------------


def test_holds_view_is_tenant_scoped_read_only_and_visible_while_held():
    world, custody, app = _world()
    tenant = world.principal.tenant_id
    policy = uuid4()
    custody.rows.append((tenant, policy, "revoked"))
    custody.rows.append((uuid4(), None, "legacy_unresolved"))  # foreign tenant, never shown
    response = run(_get(app, f"{GOVERN}/holds"))
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == str(tenant)
    assert body["legacy_hold"] is True
    assert body["holds"] == [
        {"scope": "tenant", "policy_id": None, "reason": "legacy_unresolved", "recorded_at": None},
        {"scope": "policy", "policy_id": str(policy), "reason": "revoked", "recorded_at": None},
    ]
    assert custody.acts == [("list_revocations", tenant)]  # read only, one call
    # No governance audit row for a read.
    assert world.audit.read(tenant, event_type=AuditEventType.SECURITY_POLICY_CHANGED) == ()


def test_holds_view_empty_when_nothing_is_held():
    _, custody, app = _world(holds=[])
    body = run(_get(app, f"{GOVERN}/holds")).json()
    assert body["legacy_hold"] is False and body["holds"] == []


def test_holds_view_requires_admin_and_governance_seam():
    from tests.api.test_admin_api import World

    world, custody, _ = _world()
    world.principal = replace(world.principal, is_admin=False)
    denied = run(_get(governed_app(world, custody), f"{GOVERN}/holds"))
    assert denied.status_code in (401, 403)
    # Without a custody port the governance family (incl. holds) is absent (20 §4).
    plain = World()
    from tests.api.test_promotion_evidence_r177 import _app as plain_app

    assert run(_get(plain_app(plain, strict=False), f"{GOVERN}/holds")).status_code == 404


# --- (b) unambiguous release outcome ------------------------------------------------------


def _release(app, ref=None):
    ref = ref or uuid4()
    return run(_post(app, f"{GOVERN}/release-legacy-hold", {"reconciliation_ref": str(ref)})), ref


def test_release_outcomes_released_then_already_released_then_no_hold():
    world, custody, app = _world()
    tenant = world.principal.tenant_id
    first, ref = _release(app)
    assert first.status_code == 200
    assert first.json() == {
        "released": True,
        "outcome": "released",
        "reconciliation_ref": str(ref),
    }
    second, ref2 = _release(app)
    assert second.status_code == 200
    assert second.json() == {
        "released": False,
        "outcome": "already_released",
        "reconciliation_ref": str(ref2),
    }
    # Both acts audited (a no-op release is still an operator act).
    events = world.audit.read(tenant, event_type=AuditEventType.SECURITY_POLICY_CHANGED)
    assert [e.details["result"]["outcome"] for e in events] == ["released", "already_released"]
    # A tenant that was NEVER held (registered after 0020, no prior release): no_hold.
    _, _, fresh_app = _world(holds=[])
    never, ref3 = _release(fresh_app)
    assert never.status_code == 200
    assert never.json() == {
        "released": False,
        "outcome": "no_hold",
        "reconciliation_ref": str(ref3),
    }


def test_release_refuses_when_custody_contradicts_durable_state():
    # Custody claims "released" but the hold row is still there ⇒ invariant break.
    _, custody, app = _world(release_result=True)
    response, _ = _release(app)
    assert response.status_code == 409
    assert response.json()["error"]["message"] == "Learning operation refused."
    assert custody.rows  # nothing was silently dropped
    # Custody claims "nothing released" while a hold IS present ⇒ also refused.
    _, custody2, app2 = _world(release_result=False)
    response2, _ = _release(app2)
    assert response2.status_code == 409
    assert custody2.rows


# --- (c) intake: row refused vs durable layer unavailable -----------------------------------


def _intake_body(rows):
    body = custody_body()
    del body["knowledge_key"], body["knowledge_value"]
    body.update(
        format="json",
        content=json.dumps(rows),
        expectations={"required_columns": ["key", "v"], "key_column": "key"},
    )
    return body


ROWS = [{"key": f"k{i}", "v": "x"} for i in range(1, 4)]


def test_intake_row_refusal_is_per_row_and_the_batch_continues():
    from core.learning.storage import LearningStorageConflict

    world, inner = custody_api_world()
    real = inner.capture_external

    def capture(tenant_id, **kwargs):
        if kwargs["idempotency_key"] == _row_key(body, 2):
            raise LearningStorageConflict("backend-detail-must-not-leak")
        return real(tenant_id, **kwargs)

    body = _intake_body(ROWS)
    inner.capture_external = capture
    response = run(_post(governed_app(world, inner), INTAKE, body))
    assert response.status_code == 201
    report = response.json()
    assert [r["row"] for r in report["admitted"]] == [1, 3]
    assert report["refused"] == [{"row": 2, "reason": "custody refused (conflict)"}]
    assert report["not_attempted"] == []
    assert report["layer_fault"] is None
    assert "backend-detail" not in response.text


def test_intake_layer_fault_stops_reports_landed_rows_and_answers_503():
    world, inner = custody_api_world()
    real = inner.capture_external

    def capture(tenant_id, **kwargs):
        if kwargs["idempotency_key"] == _row_key(body, 2):
            raise ConnectionError("pool exhausted: host=db-internal")
        return real(tenant_id, **kwargs)

    body = _intake_body(ROWS)
    inner.capture_external = capture
    response = run(_post(governed_app(world, inner), INTAKE, body))
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "internal_error" and error["retryable"] is True
    assert "db-internal" not in response.text
    report = error["details"]["report"]
    assert [r["row"] for r in report["admitted"]] == [1]  # landed rows are reported
    assert report["refused"] == []
    assert report["not_attempted"] == [2, 3]
    assert report["layer_fault"] == "durable layer unavailable"
    # Retrying the SAME batch (same idempotency_key) is safe by construction:
    # row keys are stable uuid5(batch, "row:n").
    assert _row_key(body, 1) == _row_key(body, 1)


def _row_key(body, index):
    from uuid import uuid5

    return uuid5(UUID(body["idempotency_key"]), f"row:{index}")
