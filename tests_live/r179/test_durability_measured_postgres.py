"""R179 4.4 DURABILITY MEASURED — real process, real SIGKILL, real restart, four pillars.

Each pillar is a MEASUREMENT, not an assertion of hope. A pillar that dies with the
process is reported as a finding (evidence/r179_findings_ledger.md), never rephrased.
The test itself passes when the measurement completes; verdicts are written to
evidence/r179/durability_measured.json by the test (latest run; the pre-4.5 run is
kept as durability_measured_before.json) and are the deliverable.

Pillars:
  P1 durable knowledge injected into a later answer   (GOLD memory → context_provenance)
  P2 conversation continuity                          (history blocks after restart)
  P3 audit survivability                              (GET /v1/admin/audit total_recorded)
  P4 usage accounting                                 (GET /v1/usage used units)
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx

from tests_live.r179.test_deploy_truth_postgres import (  # noqa: F401
    alembic,
    cluster,
    fresh_database,
)

ROOT = os.path.realpath(os.path.join(os.path.dirname(__file__), "../.."))
SAMPLES = "/v1/admin/learning/samples"
EVIDENCE = os.path.join(ROOT, "evidence", "r179", "durability_measured.json")


def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Server:
    """A REAL ``python -m apps.main`` OS process; SIGKILL leaves no shutdown hook."""

    def __init__(self, env, port, log_path):
        self.env, self.port, self.log_path, self.process = env, port, log_path, None

    def __enter__(self):
        self.log = open(self.log_path, "a", encoding="utf-8")  # noqa: SIM115
        self.process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "apps.main"],
            env={**self.env, "HOST": "127.0.0.1", "PORT": str(self.port), "LOG_LEVEL": "warning"},
            stdout=self.log,
            stderr=subprocess.STDOUT,
            cwd=ROOT,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"server exited early: {self.process.returncode}")
            try:
                if httpx.get(f"{self.base}/healthz", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.1)
        raise AssertionError("server did not become live")

    def __exit__(self, *_):
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=30)
        self.log.close()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def kill(self):
        self.process.send_signal(signal.SIGKILL)
        return self.process.wait(timeout=30)

    def call(self, method, path, headers=None, body=None):
        return httpx.request(method, f"{self.base}{path}", headers=headers, json=body, timeout=60)


def _admin_session(server, log_path, email, password):
    registered = server.call(
        "POST",
        "/v1/auth/register",
        body=dict(email=email, password=password, preferred_language="en"),
    )
    assert registered.status_code == 201, registered.text
    server.log.flush()
    with open(log_path, encoding="utf-8") as captured:
        issued = [
            json.loads(line)
            for line in captured
            if line.startswith("{") and "email_verification_token_issued" in line
        ]
    token = next(i["token"] for i in issued if i["email"] == email)
    assert server.call("POST", "/v1/auth/verify", body={"token": token}).status_code == 200
    login = server.call("POST", "/v1/auth/login", body=dict(email=email, password=password))
    assert login.status_code == 200
    return {"Authorization": f"Bearer {login.json()['token']}"}, registered.json()["tenant_id"]


def _provenance(execution):
    for artifact in execution["result"]["artifacts"]:
        if artifact.get("type") == "context_provenance":
            return artifact
    return None


def test_four_pillars_across_real_sigkill_restart(cluster):  # noqa: F811
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL, PASSWORD

    _, url = fresh_database(cluster)
    assert alembic(url, "upgrade", "head").returncode == 0  # the REAL schema, no create_all
    port = _free_port()
    log_path = os.path.join(os.environ["TMPDIR"], f"r179_durability_{port}.log")
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TMPDIR": os.environ["TMPDIR"],
        "PYTHONPATH": ROOT,
        "LANG": "C.UTF-8",
        "DATABASE_URL": url,
        "ADMIN_EMAILS": ADMIN_EMAIL,
    }
    policy = uuid4()
    conversation = str(uuid4())
    verdicts = {}

    with Server(env, port, log_path) as boot:
        headers, tenant = _admin_session(boot, log_path, ADMIN_EMAIL, PASSWORD)
        # P3 baseline: LOGIN is audited in THIS process; does it outlive it?
        audit_boot = boot.call("GET", "/v1/admin/audit", headers).json()["total_recorded"]
        assert boot.kill() == -9

    env["LEARNING_STORAGE_POLICIES"] = json.dumps(
        [dict(tenant_id=tenant, policy_id=str(policy), retention_seconds=3600)]
    )
    # P1 second arm: the ONE HTTP-reachable memory writer (13 §6 preference
    # learning, operator opt-in) — repeated explicit language facts become a
    # memory item that later answers carry as a memory block.
    env["PREFERENCE_LEARNING_ALLOWED"] = "1"
    with Server(env, port, log_path) as first:
        # --- P1 arrange: a GOLD item via the governed lifecycle -------------------
        refs = dict(policy_id=str(policy), rights_ref=str(uuid4()), idempotency_key=str(uuid4()))
        captured = first.call(
            "POST",
            SAMPLES,
            headers,
            dict(
                **refs, knowledge_key="durability.fact", knowledge_value={"answer": "durable gold"}
            ),
        )
        assert captured.status_code == 201, captured.text
        sid = captured.json()["id"]
        assert first.call("POST", f"{SAMPLES}/{sid}/scan", headers, {}).status_code == 200
        assert (
            first.call("POST", f"{SAMPLES}/{sid}/sanitize", headers, {"passed": True}).status_code
            == 200
        )
        graded = first.call(
            "POST", f"{SAMPLES}/{sid}/evaluate", headers, {"output": {"answer": "durable gold"}}
        )
        assert graded.status_code == 200 and graded.json()["evaluated"] is True
        admitted = first.call(
            "POST",
            f"{SAMPLES}/{sid}/admit",
            headers,
            dict(
                privacy_policy_allows=True,
                tenant_user_policy_allows=True,
                sensitive_data_handled=True,
                not_poisoned=True,
            ),
        )
        assert admitted.status_code == 200, admitted.text
        verdicts["p1_admitted"] = admitted.json().get("admitted"), admitted.json().get("reason")
        promoted = first.call(
            "POST",
            f"{SAMPLES}/{sid}/promote",
            headers,
            dict(
                offline_eval_pass=True,
                regression_pass=True,
                security_eval_pass=True,
                shadow_performance_acceptable=True,
                canary_performance_acceptable=True,
                rollback_plan_exists=True,
                approval_required=True,
                admin_approved=True,
            ),
        )
        verdicts["p1_promote_status"] = promoted.status_code
        verdicts["p1_promote_body"] = promoted.json() if promoted.status_code != 500 else None
        # --- P2 arrange: turns in one conversation. F-R179-01: on the durable
        # profile this path answers 500 (in-memory conversation store vs the
        # executions FK). Measure, record, continue with a plain execute so
        # P1/P3/P4 are still measured; never mask the failure.
        conv_status = []
        for turn in ("first turn", "second turn"):
            run = first.call(
                "POST", "/v1/execute", headers, {"ask": turn, "conversation_id": conversation}
            )
            conv_status.append(run.status_code)
        verdicts["p2_conversation_execute_status"] = conv_status
        for _ in range(2):
            fact = first.call(
                "POST", "/v1/execute", headers, {"ask": "fact", "context": {"language": "ar"}}
            )
            assert fact.status_code == 200, fact.text
        before = first.call("POST", "/v1/execute", headers, {"ask": "before kill"})
        assert before.status_code == 200, before.text
        prefs_before = first.call("GET", "/v1/memory/preferences", headers)
        prov_before = _provenance(before.json())
        audit_before = first.call("GET", "/v1/admin/audit", headers).json()["total_recorded"]
        usage_before = first.call("GET", "/v1/usage", headers).json()
        learned_before = first.call("GET", "/v1/admin/learning/learned", headers).json()
        assert first.kill() == -9

    with Server(env, port, log_path) as second:
        after_conv = second.call(
            "POST", "/v1/execute", headers, {"ask": "after kill", "conversation_id": conversation}
        )
        verdicts["p2_conversation_execute_status_after_restart"] = after_conv.status_code
        after = second.call("POST", "/v1/execute", headers, {"ask": "after kill"})
        prefs_after = second.call("GET", "/v1/memory/preferences", headers)
        prov_after = _provenance(after.json()) if after.status_code == 200 else None
        audit_after = second.call("GET", "/v1/admin/audit", headers).json()["total_recorded"]
        usage_after = second.call("GET", "/v1/usage", headers).json()
        learned_after = second.call("GET", "/v1/admin/learning/learned", headers).json()
        sample_after = second.call("GET", f"{SAMPLES}/{sid}", headers)

    def blocks(p, kind):
        return (
            None
            if p is None
            else sum(1 for b in p.get("memory_blocks", []))
            if kind == "memory"
            else p.get(kind)
        )

    measured = {
        "commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
        ).stdout.strip(),  # noqa: S603, S607
        "method": (
            "python -m apps.main OS process over TCP; SIGKILL -9 between phases; "
            "DATABASE_URL on a fresh real-alembic schema"
        ),
        "arrange": verdicts,
        "P1_knowledge_injected": {
            "learned_keys_before": learned_before,
            "learned_keys_after": learned_after,
            "gold_blocks_before": blocks(prov_before, "gold_blocks"),
            "gold_blocks_after": blocks(prov_after, "gold_blocks"),
            "memory_blocks_before": blocks(prov_before, "memory"),
            "memory_blocks_after": blocks(prov_after, "memory"),
            "preference_items_before": prefs_before.json()
            if prefs_before.status_code == 200
            else prefs_before.status_code,
            "preference_items_after": prefs_after.json()
            if prefs_after.status_code == 200
            else prefs_after.status_code,
            "custody_row_after_status": sample_after.status_code,
            "custody_level_after": sample_after.json().get("sample", {}).get("verification_level")
            if sample_after.status_code == 200
            else None,
        },
        "P2_conversation_continuity": {
            "blocks_total_before": blocks(prov_before, "blocks_total"),
            "blocks_total_after": blocks(prov_after, "blocks_total"),
            "execute_after_status": after.status_code,
            "execute_after_error": None if after.status_code == 200 else after.json(),
        },
        "P3_audit_survivability": {
            "total_after_login_in_boot_process": audit_boot,
            "total_before_kill": audit_before,
            "total_after_restart": audit_after,
        },
        "P4_usage_accounting": {
            "summary_before_kill": usage_before,
            "summary_after_restart": usage_after,
        },
    }
    os.makedirs(os.path.dirname(EVIDENCE), exist_ok=True)
    with open(EVIDENCE, "w", encoding="utf-8") as out:
        json.dump(measured, out, indent=2, default=str)
    # The measurement is the deliverable; the test only asserts it was taken end to end.
    assert audit_after is not None and usage_after is not None
