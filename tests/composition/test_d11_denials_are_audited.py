"""R168 D-11 — denials leave audit rows (20 §9) readable by the tenant's admin.

Defect (ledger D-11): after 30+ denials ``GET /v1/admin/audit`` listed only
``login`` — ``PERMISSION_DENIED`` and ``CROSS_TENANT_ACCESS_DENIED`` had zero
emitters. Contract now:

- a NON-ADMIN session hitting ``/v1/admin/*`` keeps its constant 403 AND one
  ``permission_denied`` row is written in the CALLER's tenant (method, path,
  reason — never the request body);
- a caller referencing ANOTHER tenant's project on ``/v1/execute`` keeps the
  D-08 byte-identical 404 AND one ``cross_tenant_access_denied`` row is written
  in the ACTOR's tenant (the reference as given; the target tenant is unknowable
  by design — absent == foreign, 20 §6 — so nothing is written elsewhere);
- an admin of that tenant reads the rows through ``GET /v1/admin/audit``.

The response bodies are asserted UNCHANGED (no oracle is introduced).
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from typing import Any

import httpx
import pytest

from apps.composition import runtime as runtime_module
from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.audit.memory import InMemoryAuditLog

ADMIN_EMAIL = "d11-admin@example.test"
USER_EMAIL = "d11-user@example.test"
OTHER_EMAIL = "d11-other@example.test"
PASSWORD = "correct horse battery staple"


_CAPTURED: list[InMemoryAuditLog] = []


class _CapturingAuditLog(InMemoryAuditLog):
    """The runtime's ONE audit log, captured so the test can read the port view."""

    def __init__(self) -> None:
        super().__init__()
        _CAPTURED.append(self)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    _CAPTURED.clear()
    monkeypatch.setattr(runtime_module, "InMemoryAuditLog", _CapturingAuditLog)


def _audit_log() -> InMemoryAuditLog:
    assert len(_CAPTURED) == 1, "runtime must build exactly one audit log"
    return _CAPTURED[0]


def _session(profile: RuntimeProfile, email: str) -> str:
    identity = profile.identity
    assert identity is not None
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        identity.register(email, PASSWORD, "en")
    token = json.loads(stream.getvalue().strip().splitlines()[-1])["token"]
    identity.verify_email(token)
    return identity.login(email, PASSWORD).token


async def _req(
    profile: RuntimeProfile,
    method: str,
    path: str,
    token: str,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=profile.app), base_url="http://test"
    ) as client:
        return await client.request(
            method, path, json=json_body, headers={"Authorization": f"Bearer {token}"}
        )


def _audit_rows(
    profile: RuntimeProfile, tenant_token: str, event_type: str
) -> list[dict[str, Any]]:
    """Read the audit log directly for the tenant of ``tenant_token`` (port view)."""
    identity = profile.identity
    assert identity is not None
    session = identity.resolve_session(tenant_token)
    rows = _audit_log().read(session.tenant_id)
    return [r.model_dump(mode="json") for r in rows if r.event_type.value == event_type]


def test_non_admin_denial_writes_permission_denied_in_callers_tenant() -> None:
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    user = _session(profile, USER_EMAIL)
    before = _audit_rows(profile, user, "permission_denied")

    r = asyncio.run(_req(profile, "POST", "/v1/admin/scenarios", user, {"secret": "do-not-echo"}))
    assert (r.status_code, r.json()["error"]["code"]) == (403, "unauthorized")

    rows = _audit_rows(profile, user, "permission_denied")
    assert len(rows) == len(before) + 1, rows
    row = rows[-1]
    assert row["details"]["path"] == "/v1/admin/scenarios"
    assert row["details"]["method"] == "POST"
    assert row["details"]["reason"] == "admin_required"
    assert "do-not-echo" not in json.dumps(row)


def test_foreign_project_reference_writes_cross_tenant_denied_in_actors_tenant() -> None:
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    owner = _session(profile, USER_EMAIL)
    actor = _session(profile, OTHER_EMAIL)
    pid = asyncio.run(_req(profile, "POST", "/v1/projects", owner, {"name": "ops"})).json()[
        "project_id"
    ]
    ref = asyncio.run(_req(profile, "GET", f"/v1/projects/{pid}", actor))
    assert ref.status_code == 404

    r = asyncio.run(
        _req(profile, "POST", "/v1/execute", actor, {"ask": "Reply OK.", "project_id": pid})
    )
    assert (r.status_code, r.content) == (404, ref.content)  # D-08 byte-identical, unchanged

    rows = _audit_rows(profile, actor, "cross_tenant_access_denied")
    assert len(rows) == 1, rows
    assert rows[0]["details"] == {
        "path": "/v1/execute",
        "method": "POST",
        "resource": "project",
        "reference": pid,
    }
    # Nothing is written into the OWNER's tenant: the target is unknowable
    # by design (absent == foreign) and an owner-side row would be an oracle.
    assert _audit_rows(profile, owner, "cross_tenant_access_denied") == []


def test_unknown_and_malformed_project_references_are_also_recorded() -> None:
    # The gate cannot distinguish foreign from unknown (20 §6) — every
    # unresolved reference is a denied access to a resource the caller does
    # not own, and is recorded identically.
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    actor = _session(profile, OTHER_EMAIL)
    for reference in ("00000000-0000-4000-8000-000000000000", "not-a-uuid"):
        r = asyncio.run(
            _req(profile, "POST", "/v1/execute", actor, {"ask": "x", "project_id": reference})
        )
        assert r.status_code == 404
    rows = _audit_rows(profile, actor, "cross_tenant_access_denied")
    assert [row["details"]["reference"] for row in rows] == [
        "00000000-0000-4000-8000-000000000000",
        "not-a-uuid",
    ]


def test_tenant_admin_reads_denial_rows_over_http() -> None:
    # The admin's OWN denials-in-tenant view: an admin whose tenant produced a
    # denial sees it on GET /v1/admin/audit. A personal tenant has exactly one
    # user, so the denial is provoked by the admin's own session on a route
    # that resolves a foreign reference.
    profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
    owner = _session(profile, USER_EMAIL)
    admin = _session(profile, ADMIN_EMAIL)
    pid = asyncio.run(_req(profile, "POST", "/v1/projects", owner, {"name": "ops"})).json()[
        "project_id"
    ]
    r = asyncio.run(_req(profile, "POST", "/v1/execute", admin, {"ask": "x", "project_id": pid}))
    assert r.status_code == 404

    audit = asyncio.run(
        _req(profile, "GET", "/v1/admin/audit?event_type=cross_tenant_access_denied", admin)
    )
    assert audit.status_code == 200
    events = audit.json()["events"]
    assert len(events) == 1
    assert events[0]["details"]["reference"] == pid
    assert events[0]["actor_id"] is not None
