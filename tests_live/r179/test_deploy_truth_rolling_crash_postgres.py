"""R179 4.6-b / 4.6-c DEPLOY TRUTH — rolling-upgrade pair and crash DURING a write.

4.6-b  Rolling pair: an OLD writer binary (commit 2c197229 = the last commit before
       migration 0020 existed; checked out as a git worktree) and the NEW binary run
       against the SAME database migrated to 0020. Expected truth (OPERATIONS.md §8.1):
       the old writer must be refused or stopped — it must not land a custody row
       that bypasses the 0020 legacy hold. The measurement records exactly what the
       old writer could and could not do; nothing is masked.

4.6-c  Crash during a write: a custody capture is made to block INSIDE its transaction
       (statement-level trigger sleeping on `learning_samples` insert) and the writer
       process is SIGKILLed mid-write. After restart: zero orphan rows (no
       `learning_samples` without `learning_sample_custody`, no dangling executions
       from the interrupted capture), and the same idempotency key completes cleanly.

Both use the disposable local cluster (tests_live/r179/run_local_postgres.sh).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

from tests_live.r179.test_deploy_truth_postgres import (  # noqa: F401
    ROOT,
    alembic,
    cluster,
    fresh_database,
    sql,
)
from tests_live.r179.test_durability_measured_postgres import (
    SAMPLES,
    Server,
    _admin_session,
    _free_port,
)

OLD_WRITER_COMMIT = "2c197229"
OLD_WRITER_DIR = os.path.join(ROOT, ".venv", f"old_writer_{OLD_WRITER_COMMIT}")
EVIDENCE = os.path.join(ROOT, "evidence", "r179", "deploy_truth_rolling_crash.json")


def _base_env(url, admin_email):
    return {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "TMPDIR": os.environ["TMPDIR"],
        "LANG": "C.UTF-8",
        "DATABASE_URL": url,
        "ADMIN_EMAILS": admin_email,
    }


def _ensure_old_writer_worktree():
    if not os.path.isdir(os.path.join(OLD_WRITER_DIR, "apps")):
        subprocess.run(  # noqa: S603, S607
            ["git", "worktree", "add", "--detach", OLD_WRITER_DIR, OLD_WRITER_COMMIT],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    head = subprocess.run(  # noqa: S603, S607
        ["git", "rev-parse", "--short", "HEAD"], cwd=OLD_WRITER_DIR, capture_output=True, text=True
    ).stdout.strip()
    assert head.startswith(OLD_WRITER_COMMIT[:7]), head
    return OLD_WRITER_DIR


class OldWriter(Server):
    """The pre-0020 binary, launched from its own worktree (same venv, old source)."""

    def __init__(self, env, port, log_path, root):
        super().__init__({**env, "PYTHONPATH": root}, port, log_path)
        self.root = root

    def __enter__(self):
        self.log = open(self.log_path, "a", encoding="utf-8")  # noqa: SIM115
        self.process = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "apps.main"],
            env={**self.env, "HOST": "127.0.0.1", "PORT": str(self.port), "LOG_LEVEL": "warning"},
            stdout=self.log,
            stderr=subprocess.STDOUT,
            cwd=self.root,
        )
        deadline = time.monotonic() + 60
        import httpx

        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                return self  # refused at boot — a valid measured outcome
            try:
                if httpx.get(f"{self.base}/healthz", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                time.sleep(0.1)
        raise AssertionError("old writer neither booted nor exited")


def _capture_body(policy, key="rolling.fact"):
    return dict(
        policy_id=str(policy),
        rights_ref=str(uuid4()),
        idempotency_key=str(uuid4()),
        knowledge_key=key,
        knowledge_value={"answer": key},
    )


def _row_counts(url):
    return {
        "learning_samples": sql(url, "SELECT count(*) FROM learning_samples")[0][0],
        "learning_sample_custody": sql(url, "SELECT count(*) FROM learning_sample_custody")[0][0],
        "orphan_samples_without_custody": sql(
            url,
            "SELECT count(*) FROM learning_samples s LEFT JOIN learning_sample_custody c "
            "ON c.sample_id = s.id WHERE c.sample_id IS NULL",
        )[0][0],
        "orphan_custody_without_sample": sql(
            url,
            "SELECT count(*) FROM learning_sample_custody c LEFT JOIN learning_samples s "
            "ON s.id = c.sample_id WHERE s.id IS NULL",
        )[0][0],
        "revocations": sql(url, "SELECT count(*) FROM learning_policy_revocations")[0][0],
    }


def _write_evidence(section, payload):
    os.makedirs(os.path.dirname(EVIDENCE), exist_ok=True)
    current = {}
    if os.path.exists(EVIDENCE):
        with open(EVIDENCE, encoding="utf-8") as f:
            current = json.load(f)
    current[section] = payload
    current["git_head"] = subprocess.run(  # noqa: S603, S607
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    with open(EVIDENCE, "w", encoding="utf-8") as out:
        json.dump(current, out, indent=2, default=str)


# --- 4.6-b rolling-upgrade pair -----------------------------------------------------


def test_rolling_pair_old_writer_is_refused_or_stopped(cluster):  # noqa: F811
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL, PASSWORD

    old_root = _ensure_old_writer_worktree()
    _, url = fresh_database(cluster)
    # Phase 0: the OLD binary's schema world (0019) — it registers the tenant.
    assert alembic(url, "upgrade", "0019").returncode == 0
    port_old, port_new = _free_port(), _free_port()
    log_old = os.path.join(os.environ["TMPDIR"], f"r179_old_writer_{port_old}.log")
    log_new = os.path.join(os.environ["TMPDIR"], f"r179_new_writer_{port_new}.log")
    policy = uuid4()
    verdict = {"old_writer_commit": OLD_WRITER_COMMIT}

    with OldWriter(_base_env(url, ADMIN_EMAIL), port_old, log_old, old_root) as old_boot:
        assert old_boot.process.poll() is None, "old writer must boot on its own schema"
        headers, tenant = _admin_session(old_boot, log_old, ADMIN_EMAIL, PASSWORD)
        env_policy = json.dumps(
            [dict(tenant_id=tenant, policy_id=str(policy), retention_seconds=3600)]
        )
    # Phase 1: migrate to 0020 while the old writer is STOPPED (the documented
    # procedure); the tenant that existed gets the legacy hold.
    assert alembic(url, "upgrade", "head").returncode == 0
    verdict["hold_rows_after_0020"] = sql(
        url,
        "SELECT count(*) FROM learning_policy_revocations WHERE tenant_id = :t "
        "AND policy_id IS NULL AND reason = 'legacy_unresolved'",
        t=tenant,
    )[0][0]
    assert verdict["hold_rows_after_0020"] == 1

    # Phase 2: ROLLING PAIR — an operator (wrongly) restarts the OLD binary next to
    # the NEW one on the 0020 database. Measure what each can do.
    env_old = {**_base_env(url, ADMIN_EMAIL), "LEARNING_STORAGE_POLICIES": env_policy}
    env_new = {**env_old, "PYTHONPATH": ROOT}
    with (
        OldWriter(env_old, port_old, log_old, old_root) as old,
        Server(env_new, port_new, log_new) as new,
    ):
        verdict["old_writer_booted_on_0020"] = old.process.poll() is None
        if verdict["old_writer_booted_on_0020"]:
            old_login = old.call(
                "POST", "/v1/auth/login", body=dict(email=ADMIN_EMAIL, password=PASSWORD)
            )
            old_headers = {"Authorization": f"Bearer {old_login.json()['token']}"}
            old_capture = old.call("POST", SAMPLES, old_headers, _capture_body(policy, "old.fact"))
            verdict["old_writer_capture_status"] = old_capture.status_code
            verdict["old_writer_capture_body"] = (
                old_capture.json()
                if old_capture.headers.get("content-type", "").startswith("application/json")
                else old_capture.text[:200]
            )
        else:
            verdict["old_writer_exit_code"] = old.process.returncode
            verdict["old_writer_capture_status"] = None
        new_login = new.call(
            "POST", "/v1/auth/login", body=dict(email=ADMIN_EMAIL, password=PASSWORD)
        )
        new_headers = {"Authorization": f"Bearer {new_login.json()['token']}"}
        held = new.call("POST", SAMPLES, new_headers, _capture_body(policy, "new.fact.held"))
        verdict["new_writer_capture_under_hold_status"] = held.status_code
        # The old writer must be STOPPED before the hold is released (§8.1).
        old_stopped = old.kill() if old.process.poll() is None else old.process.returncode
        verdict["old_writer_stopped_signal"] = old_stopped
        released = new.call(
            "POST",
            "/v1/admin/learning/custody/release-legacy-hold",
            new_headers,
            {"reconciliation_ref": str(uuid4())},
        )
        verdict["release_status"] = released.status_code
        verdict["release_body"] = released.json()
        after = new.call("POST", SAMPLES, new_headers, _capture_body(policy, "new.fact"))
        verdict["new_writer_capture_after_release_status"] = after.status_code

    verdict["rows"] = _row_counts(url)
    verdict["custody_rows_by_key"] = [
        r[0]
        for r in sql(
            url,
            "SELECT s.id::text FROM learning_sample_custody c JOIN learning_samples s "
            "ON s.id = c.sample_id ORDER BY c.created_at",
        )
    ]
    _write_evidence("rolling_pair", verdict)
    # Binding truths: the hold blocked EVERY writer while present; the old writer
    # landed NOTHING that survives the hold; the new writer works after release.
    assert verdict["new_writer_capture_under_hold_status"] == 404
    assert verdict["old_writer_capture_status"] in (None, 404, 409, 422, 500)
    assert verdict["release_status"] == 200 and verdict["release_body"].get("released") is True
    assert verdict["new_writer_capture_after_release_status"] == 201
    assert verdict["rows"]["orphan_samples_without_custody"] == 0
    assert verdict["rows"]["orphan_custody_without_sample"] == 0
    # Exactly the post-release capture landed (the hold refused the rest).
    assert verdict["rows"]["learning_sample_custody"] == 1


# --- 4.6-c crash DURING a write ----------------------------------------------------


SLOW_TRIGGER = """
CREATE OR REPLACE FUNCTION r179_slow_insert() RETURNS trigger AS $$
BEGIN PERFORM pg_sleep(8); RETURN NEW; END $$ LANGUAGE plpgsql;
CREATE TRIGGER r179_slow_learning_samples BEFORE INSERT ON learning_samples
FOR EACH ROW EXECUTE FUNCTION r179_slow_insert();
"""


def test_crash_during_write_leaves_zero_orphans(cluster):  # noqa: F811
    from tests.composition.test_admin_console_runtime import ADMIN_EMAIL, PASSWORD

    _, url = fresh_database(cluster)
    assert alembic(url, "upgrade", "head").returncode == 0
    port = _free_port()
    log_path = os.path.join(os.environ["TMPDIR"], f"r179_crash_write_{port}.log")
    policy = uuid4()
    verdict = {}

    with Server(_base_env(url, ADMIN_EMAIL), port, log_path) as boot:
        headers, tenant = _admin_session(boot, log_path, ADMIN_EMAIL, PASSWORD)
        boot.kill()
    # Tenant registered AFTER 0020 ⇒ no legacy hold; captures are admissible.
    env = {
        **_base_env(url, ADMIN_EMAIL),
        "PYTHONPATH": ROOT,
        "LEARNING_STORAGE_POLICIES": json.dumps(
            [dict(tenant_id=tenant, policy_id=str(policy), retention_seconds=3600)]
        ),
    }
    body = _capture_body(policy, "crash.fact")
    for statement in [s for s in SLOW_TRIGGER.strip().split(";\n") if s.strip()]:
        sql(url, statement)
    verdict["before"] = _row_counts(url)

    with Server(env, port, log_path) as writer:
        login = writer.call(
            "POST", "/v1/auth/login", body=dict(email=ADMIN_EMAIL, password=PASSWORD)
        )
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        outcome = {}

        def fire():
            try:
                r = writer.call("POST", SAMPLES, headers, body)
                outcome["status"] = r.status_code
            except Exception as exc:  # noqa: BLE001 — connection dies with the process
                outcome["error"] = type(exc).__name__

        t = threading.Thread(target=fire)
        t.start()
        # Wait until the write is provably INSIDE its transaction (sleeping in the trigger).
        deadline = time.monotonic() + 15
        in_flight = 0
        while time.monotonic() < deadline and not in_flight:
            in_flight = sql(
                url,
                "SELECT count(*) FROM pg_stat_activity WHERE state = 'active' "
                "AND query ILIKE '%INSERT INTO learning_samples%'",
            )[0][0]
            time.sleep(0.1)
        verdict["write_in_flight_when_killed"] = in_flight
        assert in_flight >= 1, "the capture never reached the learning_samples insert"
        verdict["kill_signal"] = writer.kill()
        t.join(timeout=30)
        verdict["client_outcome"] = outcome

    # Let the server backend notice the dead client and roll back.
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        active = sql(
            url,
            "SELECT count(*) FROM pg_stat_activity WHERE state <> 'idle' "
            "AND query ILIKE '%learning_samples%' AND pid <> pg_backend_pid()",
        )[0][0]
        if active == 0:
            break
        time.sleep(0.2)
    sql(url, "DROP TRIGGER IF EXISTS r179_slow_learning_samples ON learning_samples")
    verdict["after_crash"] = _row_counts(url)

    with Server(env, port, log_path) as restarted:
        login = restarted.call(
            "POST", "/v1/auth/login", body=dict(email=ADMIN_EMAIL, password=PASSWORD)
        )
        headers = {"Authorization": f"Bearer {login.json()['token']}"}
        retry = restarted.call("POST", SAMPLES, headers, body)  # SAME idempotency key
        verdict["retry_same_key_status"] = retry.status_code
        again = restarted.call("POST", SAMPLES, headers, body)
        verdict["retry_again_status"] = again.status_code
        verdict["retry_same_id"] = (
            retry.json().get("id") == again.json().get("id")
            if retry.status_code in (200, 201) and again.status_code in (200, 201)
            else None
        )
    verdict["after_restart"] = _row_counts(url)
    _write_evidence("crash_during_write", verdict)

    assert verdict["client_outcome"].get("status") is None  # the client never got a 201
    assert verdict["after_crash"]["learning_samples"] == 0
    assert verdict["after_crash"]["learning_sample_custody"] == 0
    assert verdict["after_crash"]["orphan_samples_without_custody"] == 0
    assert verdict["retry_same_key_status"] == 201
    assert verdict["retry_again_status"] in (200, 201) and verdict["retry_same_id"] is True
    assert verdict["after_restart"]["learning_sample_custody"] == 1
    assert verdict["after_restart"]["orphan_samples_without_custody"] == 0
    assert verdict["after_restart"]["orphan_custody_without_sample"] == 0
