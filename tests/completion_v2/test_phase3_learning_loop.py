"""Completion program v2 — Phase 3 (D-5): the bounded governed learning loop, HTTP only.

C-14 capture FROM a real execution (``source_execution_id``) → C-15 promotion whose
artefact-backed conditions are RESOLVED from real records (the lifecycle's own
evaluation record — deterministic + SECURITY grader rows — and a real scenario
replay execution) → GOLD → memory activation → C-16 a later ``/v1/execute``
carries ``context_provenance.gold_blocks == 1`` → C-17 the dashboard measures it.
Real runtime profile (``build_runtime_profile``), local echo adapter, strict
promotion evidence (served profiles never accept self-asserted passes).
"""

from __future__ import annotations

from typing import Any

import httpx

from tests.completion_v2.test_phase12_runtime import ADMIN, CSRF, _bearer, _client, _profile, run

ASK = "what is the rollback procedure for a failed deploy"
KEY = "ops.rollback_procedure"


def _artifact(body: dict[str, Any]) -> dict[str, Any]:
    artifacts = body["result"]["artifacts"]
    assert len(artifacts) == 1 and artifacts[0]["type"] == "context_provenance"
    return dict(artifacts[0])


async def _close_the_loop(c: httpx.AsyncClient, hdr: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    before = await c.post("/v1/execute", json={"ask": ASK}, headers=hdr)
    assert before.status_code == 200, before.text
    out["before"] = _artifact(before.json())
    exec_id = before.json()["execution_id"]

    cap = await c.post(
        "/v1/admin/learning/samples",
        json={
            "knowledge_key": KEY,
            "knowledge_value": {"procedure": "revert tag, redeploy previous artefact, verify"},
            "source_execution_id": exec_id,
        },
        headers=hdr,
    )
    assert cap.status_code == 201, cap.text
    assert cap.json()["source_execution_id"] == exec_id
    sid = cap.json()["id"]

    ev = await c.post(
        f"/v1/admin/learning/samples/{sid}/evaluate",
        json={"output": {"text": "revert tag; redeploy; verify"}},
        headers=hdr,
    )
    assert ev.status_code == 200 and ev.json()["evaluated"] is True, ev.text
    eval_id = ev.json()["evaluation_id"]
    assert eval_id is not None
    record = await c.get(f"/v1/admin/evaluations/{eval_id}", headers=hdr)
    assert record.status_code == 200
    graders = {(g["type"], g["passed"]) for g in record.json()["graders"]}
    assert ("security", True) in graders  # one record carries the SECURITY row
    assert record.json()["execution_id"] == exec_id

    for step, body in (
        ("scan", None),
        ("sanitize", {"passed": True}),
        (
            "admit",
            {
                "privacy_policy_allows": True,
                "tenant_user_policy_allows": True,
                "sensitive_data_handled": True,
                "not_poisoned": True,
            },
        ),
    ):
        r = await c.post(f"/v1/admin/learning/samples/{sid}/{step}", json=body, headers=hdr)
        assert r.status_code == 200, (step, r.text)
    assert r.json()["admitted"] is True

    sv = await c.post(
        "/v1/admin/scenarios", json={"name": "rollback-regression", "ask": ASK}, headers=hdr
    )
    assert sv.status_code == 201, sv.text
    rp = await c.post(f"/v1/admin/scenarios/{sv.json()['scenario_id']}/replay", headers=hdr)
    assert rp.status_code == 200 and rp.json()["passed"] is True, rp.text
    out["sample_id"], out["evaluation_id"], out["regression_execution_id"] = (
        sid,
        eval_id,
        rp.json()["execution_id"],
    )
    return out


class TestC14C15C16GoldReachesProduction:
    def test_evidence_backed_promotion_activates_gold_in_a_later_execution(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                hdr = {**await _bearer(c, ADMIN), **CSRF}
                loop = await _close_the_loop(c, hdr)
                assert loop["before"]["gold_blocks"] == 0
                sid = loop["sample_id"]
                promote = await c.post(
                    f"/v1/admin/learning/samples/{sid}/promote",
                    json={
                        "rollback_plan_exists": True,
                        "approval_required": True,
                        "admin_approved": True,
                        "shadow_performance_acceptable": True,
                        "canary_performance_acceptable": True,
                        "evidence_refs": {
                            "evaluation_id": loop["evaluation_id"],
                            "security_evaluation_id": loop["evaluation_id"],
                            "regression_execution_id": loop["regression_execution_id"],
                        },
                    },
                    headers=hdr,
                )
                assert promote.status_code == 201, promote.text
                body = promote.json()
                assert body["promoted"] is True
                resolved = body["evidence"]["resolved"]
                assert body["evidence"]["strict"] is True
                for condition in ("offline_eval_pass", "security_eval_pass", "regression_pass"):
                    assert resolved[condition]["held"] is True, resolved
                assert resolved["regression_pass"]["ref"] == loop["regression_execution_id"]

                after = await c.post("/v1/execute", json={"ask": ASK}, headers=hdr)
                assert after.status_code == 200
                prov = _artifact(after.json())
                assert prov["gold_blocks"] == 1
                assert prov["memory_blocks"][0]["source"] == "learning.gold"
                assert prov["memory_blocks"][0]["memory_id"] == body["memory_item_id"]
                # the tenant-facing run view carries the same provenance (C-16)
                status = await c.get(f"/v1/executions/{after.json()['execution_id']}", headers=hdr)
                assert status.status_code == 200
                assert _artifact(status.json())["gold_blocks"] == 1

                dashboard = await c.get("/v1/admin/learning/dashboard", headers=hdr)
                assert dashboard.status_code == 200
                d = dashboard.json()
                assert d["placeholder"] is False
                assert d["gold_samples"] == 1 and d["learned_keys"] == [KEY]
                assert d["evaluations_recorded"] == 1
                assert len(d["promotion_history"]) == 1
                assert d["promotion_history"][0]["details"]["sample_id"] == sid

        run(scenario())

    def test_self_asserted_passes_without_refs_are_refused_in_the_served_profile(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with _client(profile) as c:
                hdr = {**await _bearer(c, ADMIN), **CSRF}
                loop = await _close_the_loop(c, hdr)
                promote = await c.post(
                    f"/v1/admin/learning/samples/{loop['sample_id']}/promote",
                    json={
                        "offline_eval_pass": True,
                        "regression_pass": True,
                        "security_eval_pass": True,
                        "rollback_plan_exists": True,
                        "approval_required": True,
                        "admin_approved": True,
                        "shadow_performance_acceptable": True,
                        "canary_performance_acceptable": True,
                    },
                    headers=hdr,
                )
                assert promote.status_code == 200, promote.text
                assert promote.json()["promoted"] is False
                after = await c.post("/v1/execute", json={"ask": ASK}, headers=hdr)
                assert _artifact(after.json())["gold_blocks"] == 0

        run(scenario())

    def test_foreign_tenant_cannot_capture_from_another_tenants_execution(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            # Two cookie jars: the login cookie of one principal must never ride
            # the other's requests (that is exactly what the CSRF rule refuses).
            async with _client(profile) as c, _client(profile) as c2:
                admin = {**await _bearer(c, ADMIN), **CSRF}
                other = {**await _bearer(c2, "other@completion.test"), **CSRF}
                theirs = await c2.post("/v1/execute", json={"ask": "x"}, headers=other)
                assert theirs.status_code == 200
                cap = await c.post(
                    "/v1/admin/learning/samples",
                    json={
                        "knowledge_key": "k",
                        "knowledge_value": {"v": 1},
                        "source_execution_id": theirs.json()["execution_id"],
                    },
                    headers=admin,
                )
                assert cap.status_code == 404, cap.text  # absent == foreign

        run(scenario())
