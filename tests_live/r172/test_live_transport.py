"""R172 C8 — LIVE transport proof (Groq + GitHub). NOT part of the hermetic verifier.

Every test here is SKIPPED unless the relevant secrets are present in the
environment. Secrets are read from ``os.environ`` ONLY (no literals), stored into an
``InMemorySecretManager`` and used through the same opaque ``credential_ref`` path
production uses. Nothing here prints, asserts on, or persists a secret value; the
evidence recorder writes model / latency / status / token counts only.

Run manually (keys exported in-shell, never persisted)::

    GROQ_API_KEY_1=... GROQ_API_KEY_2=... GROQ_API_KEY_3=... GROQ_API_KEY_4=... \\
    GITHUB_TOKEN=... R172_LIVE_GITHUB_REPO=https://github.com/<owner>/<throwaway>.git \\
    python -m pytest tests_live/r172 -q -p no:cacheprovider -o addopts="" -rs

``tests_live/`` sits OUTSIDE ``pyproject.toml::testpaths`` and outside every
``green_manifest.json`` slice, so ``check_repo.sh`` never collects it and the
skip budget of the gate is untouched.

GitHub side: ``R172_LIVE_GITHUB_REPO`` MUST be a throwaway repository whose default
branch is protected (PR-only). The suite refuses to run against
``general_ai_core`` by name. Live runs create real branches / pull requests there.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from apps.agent_dev.git_tools import GitToolset, RepoBindingRegistry
from apps.agent_dev.github_transport import GitHubRestTransport, parse_github_remote
from core.contracts.provider import (
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderOperation,
)
from core.contracts.publish_mode import PublishMode
from core.contracts.remote_trust import RemoteTrustGrant
from core.contracts.repo_binding import RepoBinding
from core.secrets.memory import InMemorySecretManager
from core.tools.remote_trust import RemoteTrustRegistry
from providers.real.groq import MANIFEST, GroqAdapter

GROQ_KEY_VARS = ("GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4")
LIVE_MODEL = "llama-3.1-8b-instant"
EVIDENCE = Path(os.environ.get("R172_LIVE_EVIDENCE", "evidence/r172/live_transport.txt"))
FORBIDDEN_REPO_MARKER = "general_ai_core"

present_groq_keys = [v for v in GROQ_KEY_VARS if os.environ.get(v)]
requires_groq = pytest.mark.skipif(
    not present_groq_keys, reason="no GROQ_API_KEY_n in environment — live run only"
)
requires_github = pytest.mark.skipif(
    not (os.environ.get("GITHUB_TOKEN") and os.environ.get("R172_LIVE_GITHUB_REPO")),
    reason="GITHUB_TOKEN / R172_LIVE_GITHUB_REPO not set — live run only",
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def _record(section: str, **fields: object) -> None:
    """Append ONE line of non-secret evidence (model/latency/status/tokens only)."""
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"utc": datetime.now(tz=UTC).isoformat(timespec="seconds"), "section": section}
    payload.update(fields)
    line = json.dumps(payload, sort_keys=True)
    for var in (*GROQ_KEY_VARS, "GITHUB_TOKEN"):
        value = os.environ.get(var)
        assert not value or value not in line, f"refusing to write evidence containing {var}"
    with EVIDENCE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _no_secret_in(text: str) -> None:
    for var in (*GROQ_KEY_VARS, "GITHUB_TOKEN"):
        value = os.environ.get(var)
        if value:
            assert value not in text
    assert "gsk_" not in text


# --- Groq ---------------------------------------------------------------------------


def _groq(var: str) -> tuple[GroqAdapter, str, UUID]:
    tenant_id = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant_id, os.environ[var])
    adapter = GroqAdapter(
        MANIFEST,
        secret_resolver=lambda r: secrets.resolve(tenant_id, r),
        health_credential_ref=ref,
    )
    return adapter, ref, tenant_id


def _generate(
    adapter: GroqAdapter, ref: str, tenant_id: UUID, *, timeout_ms: int = 30_000
) -> ProviderGenerateResponse:
    request = ProviderGenerateRequest(
        request_id=uuid4(),
        tenant_id=tenant_id,
        operation=ProviderOperation.GENERATE_TEXT,
        provider_model_name=LIVE_MODEL,
        credential_ref=ref,
        payload={
            "ask": "Reply with exactly the word: OK",
            "generation": {"max_tokens": 5, "temperature": 0},
        },
        timeout_ms=timeout_ms,
    )

    async def _call() -> ProviderGenerateResponse:
        # generate + aclose in ONE event loop: the adapter's pooled client is bound
        # to the loop that created it (S2), so a second asyncio.run would close it
        # on a dead loop ("Event loop is closed").
        try:
            return await adapter.generate(request)
        finally:
            await adapter.aclose()

    return run(_call())


def _error_fields(response: ProviderGenerateResponse) -> dict[str, object]:
    if response.error is None:
        return {}
    return {
        "category": response.error.category.value,
        "provider_code": response.error.provider_code,
        "retryable": response.error.retryable,
        "retry_after_ms": response.error.retry_after_ms,
    }


@requires_groq
class TestGroqLive:
    @pytest.mark.parametrize("var", present_groq_keys or ["GROQ_API_KEY_1"])
    def test_completion_per_key_is_typed_either_way(self, var: str) -> None:
        """Each key yields EITHER a real completion OR a typed, non-leaking refusal.

        Recorded honestly: on 2026-09-04 all four supplied keys answered HTTP 400
        ``organization_restricted`` (account-level block) — the adapter maps that to
        ``invalid_credential`` / non-retryable, which is the route-indicting path.
        """
        adapter, ref, tenant_id = _groq(var)
        response = _generate(adapter, ref, tenant_id)
        dumped = response.model_dump_json()
        _no_secret_in(dumped)
        _record(
            "groq.completion",
            key=var,
            model=LIVE_MODEL,
            succeeded=response.succeeded,
            latency_ms=response.latency_ms,
            total_tokens=response.usage.get("total_tokens"),
            **_error_fields(response),
        )
        if response.succeeded:
            assert isinstance(response.output.get("content"), str)
            assert response.usage.get("total_tokens", 0) > 0
        else:
            assert response.error is not None
            assert response.error.category in {
                ProviderErrorCategory.INVALID_CREDENTIAL,
                ProviderErrorCategory.RATE_LIMITED,
                ProviderErrorCategory.QUOTA_EXCEEDED,
                ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                ProviderErrorCategory.MODEL_UNAVAILABLE,
            }
            assert response.error.safe_message and "gsk_" not in response.error.safe_message

    def test_invalid_key_is_typed_refusal_without_leak(self) -> None:
        tenant_id = uuid4()
        secrets = InMemorySecretManager()
        # Structurally plausible but bogus key: proves the refusal path, not a real secret.
        ref = secrets.store(tenant_id, "gsk_" + "0" * 52)
        adapter = GroqAdapter(MANIFEST, secret_resolver=lambda r: secrets.resolve(tenant_id, r))
        response = _generate(adapter, ref, tenant_id)
        assert response.succeeded is False and response.error is not None
        assert response.error.category is ProviderErrorCategory.INVALID_CREDENTIAL
        assert response.error.retryable is False
        _no_secret_in(response.model_dump_json())
        _record("groq.invalid_key", model=LIVE_MODEL, **_error_fields(response))

    def test_timeout_is_typed_and_retryable(self) -> None:
        adapter, ref, tenant_id = _groq(present_groq_keys[0])
        response = _generate(adapter, ref, tenant_id, timeout_ms=1)
        assert response.succeeded is False and response.error is not None
        assert response.error.category is ProviderErrorCategory.TIMEOUT
        assert response.error.retryable is True
        _no_secret_in(response.model_dump_json())
        _record("groq.timeout", model=LIVE_MODEL, timeout_ms=1, **_error_fields(response))

    def test_rate_limit_shape_is_typed_when_observed(self) -> None:
        """Burst a few calls; if Groq answers 429 the adapter MUST type it as
        ``rate_limited`` + retryable + retry_after_ms. The adapter itself performs
        NO retry/backoff — that lives in ``ExecutionService`` (finding recorded);
        this test only asserts the classification when the provider emits it.
        """
        adapter, ref, tenant_id = _groq(present_groq_keys[0])
        observed: list[dict[str, object]] = []

        async def _burst() -> None:
            try:
                for _ in range(6):
                    request = ProviderGenerateRequest(
                        request_id=uuid4(),
                        tenant_id=tenant_id,
                        operation=ProviderOperation.GENERATE_TEXT,
                        provider_model_name=LIVE_MODEL,
                        credential_ref=ref,
                        payload={"ask": "OK", "generation": {"max_tokens": 1}},
                        timeout_ms=30_000,
                    )
                    response = await adapter.generate(request)
                    observed.append({"succeeded": response.succeeded, **_error_fields(response)})
                    error = response.error
                    if error and error.category is ProviderErrorCategory.RATE_LIMITED:
                        assert error.retryable is True
                        break
            finally:
                await adapter.aclose()

        run(_burst())
        categories = sorted({str(o.get("category")) for o in observed})
        _record(
            "groq.rate_limit_probe",
            model=LIVE_MODEL,
            calls=len(observed),
            categories=categories,
            observed_429="rate_limited" in categories,
            adapter_retries=0,
        )


# --- GitHub -------------------------------------------------------------------------


def _github_world(
    tmp_path: Path, *, trusted: bool, allow_direct_push: bool = False
) -> tuple[GitToolset, RepoBinding, InMemorySecretManager, GitHubRestTransport]:
    remote = os.environ["R172_LIVE_GITHUB_REPO"]
    assert FORBIDDEN_REPO_MARKER not in remote.lower(), "never target general_ai_core"
    parse_github_remote(remote)  # refuses non-github shapes early
    tenant_id = uuid4()
    secrets = InMemorySecretManager()
    ref = secrets.store(tenant_id, os.environ["GITHUB_TOKEN"])
    root = tmp_path / "work"
    root.mkdir()
    modes = {PublishMode.DRY_RUN, PublishMode.LOCAL_COMMIT_ONLY, PublishMode.PULL_REQUEST}
    if allow_direct_push:
        modes.add(PublishMode.DIRECT_PUSH)
    binding = RepoBinding(
        tenant_id=tenant_id,
        remote_url=remote,
        branch="main",
        local_root=str(root),
        credential_ref=ref,
        allowed_modes=frozenset(modes),
        label="r172-live",
    )
    registry = RepoBindingRegistry()
    registry.register(binding)
    trust = RemoteTrustRegistry()
    if trusted:
        trust.grant(
            RemoteTrustGrant(
                tenant_id=tenant_id,
                remote_url=remote,
                trusted=True,
                granted_by="r172-live-suite",
                granted_at=datetime.now(tz=UTC),
            )
        )
    transport = GitHubRestTransport()
    toolset = GitToolset(
        tenant_id=tenant_id,
        bindings=registry,
        transport=transport,
        secrets=secrets,
        trust=trust,
    )
    return toolset, binding, secrets, transport


def _write_change(binding: RepoBinding) -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    name = f"r172/live-{stamp}-{uuid4().hex[:6]}.txt"
    path = Path(binding.local_root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"R172 C8 live transport proof {stamp}\n", encoding="utf-8")
    return name


class _CountingSecrets:
    """Wraps a SecretManagerPort and counts resolve() calls."""

    def __init__(self, inner: InMemorySecretManager) -> None:
        self._inner = inner
        self.resolves = 0

    def store(self, tenant_id: UUID, secret_value: str) -> str:
        return self._inner.store(tenant_id, secret_value)

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        self.resolves += 1
        return self._inner.resolve(tenant_id, credential_ref)

    def revoke(self, tenant_id: UUID, credential_ref: str) -> None:
        self._inner.revoke(tenant_id, credential_ref)

    def exists(self, tenant_id: UUID, credential_ref: str) -> bool:
        return self._inner.exists(tenant_id, credential_ref)


@requires_github
class TestGitHubLive:
    def test_fetch_and_status(self, tmp_path: Path) -> None:
        toolset, binding, _, _ = _github_world(tmp_path, trusted=True)
        started = time.monotonic()
        fetched = run(toolset.fetch({"binding_id": str(binding.id)}))
        latency = int((time.monotonic() - started) * 1000)
        assert fetched.get("ok") is True, fetched
        assert isinstance(fetched.get("remote_head"), str) and len(fetched["remote_head"]) == 40
        status = run(toolset.status({"binding_id": str(binding.id)}))
        assert status.get("ok") is True and status["clean"] is True
        _no_secret_in(json.dumps([fetched, status]))
        _record("github.fetch_status", remote_head=fetched["remote_head"][:7], latency_ms=latency)

    def test_commit_and_publish_pull_request_yields_real_pr_url(self, tmp_path: Path) -> None:
        toolset, binding, _, _ = _github_world(tmp_path, trusted=True)
        name = _write_change(binding)
        committed = run(
            toolset.commit(
                {
                    "binding_id": str(binding.id),
                    "message": "r172 live: pull_request",
                    "paths": [name],
                }
            )
        )
        assert committed.get("ok") is True, committed
        started = time.monotonic()
        published = run(
            toolset.publish(
                {
                    "binding_id": str(binding.id),
                    "mode": "pull_request",
                    "title": "R172 C8 live transport proof",
                }
            )
        )
        latency = int((time.monotonic() - started) * 1000)
        assert published.get("ok") is True, published
        assert published["mode"] == "pull_request" and published["pushed"] is True
        url = published["pull_request_url"]
        assert isinstance(url, str) and "/pull/" in url and url.startswith("https://github.com/")
        _no_secret_in(json.dumps([committed, published]))
        _record(
            "github.publish.pull_request",
            pull_request_url=url,
            work_branch=published["branch"],
            latency_ms=latency,
        )

    def test_direct_push_disallowed_is_refused_and_remote_unmodified(self, tmp_path: Path) -> None:
        toolset, binding, _, _ = _github_world(tmp_path, trusted=True)
        before = run(toolset.fetch({"binding_id": str(binding.id)}))["remote_head"]
        name = _write_change(binding)
        run(toolset.commit({"binding_id": str(binding.id), "message": "x", "paths": [name]}))
        refused = run(toolset.publish({"binding_id": str(binding.id), "mode": "direct_push"}))
        assert refused.get("ok") is False, refused
        assert refused["code"] == "publish_mode_not_allowed"
        assert refused["suggested_mode"] == "pull_request"
        after = run(toolset.fetch({"binding_id": str(binding.id)}))["remote_head"]
        assert after == before
        _record(
            "github.publish.direct_push_disallowed",
            code=refused["code"],
            suggested_mode=refused["suggested_mode"],
            remote_head_unchanged=after == before,
        )

    def test_direct_push_to_protected_branch_is_typed(self, tmp_path: Path) -> None:
        toolset, binding, _, _ = _github_world(tmp_path, trusted=True, allow_direct_push=True)
        before = run(toolset.fetch({"binding_id": str(binding.id)}))["remote_head"]
        name = _write_change(binding)
        run(toolset.commit({"binding_id": str(binding.id), "message": "x", "paths": [name]}))
        refused = run(toolset.publish({"binding_id": str(binding.id), "mode": "direct_push"}))
        assert refused.get("ok") is False, refused
        assert refused["code"] == "remote_rejected_protected_branch"
        assert refused["suggested_mode"] == "pull_request"
        after = run(toolset.fetch({"binding_id": str(binding.id)}))["remote_head"]
        assert after == before
        _no_secret_in(json.dumps(refused))
        _record(
            "github.publish.protected_branch",
            code=refused["code"],
            suggested_mode=refused["suggested_mode"],
            remote_head_unchanged=after == before,
        )

    def test_untrusted_binding_refuses_before_any_secret_resolve(self, tmp_path: Path) -> None:
        toolset, binding, secrets, _ = _github_world(tmp_path, trusted=False)
        counting = _CountingSecrets(secrets)
        toolset.secrets = counting  # type: ignore[assignment]
        fetched = run(toolset.fetch({"binding_id": str(binding.id)}))
        assert fetched.get("ok") is False and fetched["code"] == "remote_not_trusted"
        name = _write_change(binding)
        run(toolset.commit({"binding_id": str(binding.id), "message": "x", "paths": [name]}))
        published = run(toolset.publish({"binding_id": str(binding.id), "mode": "pull_request"}))
        assert published.get("ok") is False and published["code"] == "remote_not_trusted"
        assert counting.resolves == 0
        _record(
            "github.untrusted_binding",
            fetch_code=fetched["code"],
            publish_code=published["code"],
            secret_resolves=counting.resolves,
        )

    def test_credential_never_in_artifacts(self, tmp_path: Path) -> None:
        toolset, binding, _, transport = _github_world(tmp_path, trusted=True)
        run(toolset.fetch({"binding_id": str(binding.id)}))
        artifacts = json.dumps(
            {
                "trace": [entry.model_dump(mode="json") for entry in toolset.trace],
                "transport_repr": repr(transport),
                "binding": binding.model_dump(mode="json"),
            }
        )
        _no_secret_in(artifacts)
        _record("github.no_credential_in_artifacts", checked=len(artifacts))
