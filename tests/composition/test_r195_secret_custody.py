"""R195-D (AD-2, operator APPROVED D3): the ONE shared secret custody instance is
the existing Vault `SecretManagerPort` when `VAULT_ADDR` + `VAULT_TOKEN` are set,
and the admin lifecycle receives the dev-binding seams when the dev path composes.

- Vault configured ⇒ `VaultSecretManager` (via the existing, previously uncalled
  `vault_settings_from_env` + `build_secret_manager`); half-configured ⇒ raises.
- absent ⇒ `InMemorySecretManager` (byte-identical pre-R195 posture).
- `AGENT_DEV_STATE_DIR` ⇒ a published `register_repo_binding` change is visible
  in `profile.dev_bindings` for the owning tenant.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.composition import secrets as secrets_composition
from apps.composition.dev_bindings import ENV_DEV_STATE_DIR
from apps.composition.runtime import (
    DEV_DEMO_PRINCIPAL_ENV,
    build_runtime_profile,
    secret_custody_from_env,
)
from core.secrets.memory import InMemorySecretManager
from infrastructure.secrets import VaultSecretManager
from tests.composition.test_admin_console_runtime import _admin_token
from tests.infrastructure.test_vault_secret_manager_t074 import StubKvV2

TENANT = uuid4()


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


class TestCustodySelection:
    def test_vault_bound_when_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        kv = StubKvV2()
        seen: list[dict[str, Any]] = []

        def fake_client(**kwargs: Any) -> Any:
            seen.append(kwargs)
            return SimpleNamespace(secrets=SimpleNamespace(kv=SimpleNamespace(v2=kv)))

        monkeypatch.setattr(secrets_composition.hvac, "Client", fake_client)
        custody = secret_custody_from_env(
            {"VAULT_ADDR": "https://vault.test:8200", "VAULT_TOKEN": "s.x", "VAULT_MOUNT": "kv"}
        )
        assert isinstance(custody, VaultSecretManager)
        assert seen == [{"url": "https://vault.test:8200", "token": "s.x"}]
        ref = custody.store(TENANT, "ghp_value")  # noqa: S106 — custody probe
        assert custody.resolve(TENANT, ref) == "ghp_value"
        assert custody.exists(uuid4(), ref) is False  # tenant-scoped path
        assert all(mount == "kv" for mount, _ in kv.paths)

    def test_half_configured_raises(self) -> None:
        with pytest.raises(ValueError, match="VAULT_TOKEN"):
            secret_custody_from_env({"VAULT_ADDR": "https://vault.test:8200"})

    def test_absent_is_in_memory(self) -> None:
        assert isinstance(secret_custody_from_env({}), InMemorySecretManager)


class TestLifecycleSeamsComposed:
    def test_published_binding_visible_in_dev_registry(self, tmp_path: Path) -> None:
        env = {
            "ADMIN_EMAILS": "skills-admin@example.test",
            DEV_DEMO_PRINCIPAL_ENV: "1",
            ENV_DEV_STATE_DIR: str(tmp_path / "state"),
        }
        profile = build_runtime_profile(environ=env)
        assert profile.dev_bindings is not None
        headers = {"Authorization": f"Bearer {_admin_token(profile)}"}
        (tmp_path / "wt").mkdir()
        binding = {
            "id": str(uuid4()),
            "tenant_id": str(TENANT),
            "remote_url": "https://github.com/acme/shop",
            "branch": "main",
            "local_root": str(tmp_path / "wt"),
            "credential_ref": "vault:dev-a",
        }

        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=profile.app), base_url="http://t"
            ) as c:
                r = await c.post(
                    "/v1/admin/changes",
                    json={"action": "register_repo_binding", "payload": {"binding": binding}},
                    headers=headers,
                )
                assert r.status_code == 201, r.text
                change_id = r.json()["id"]
                for step in ("validate", "preview", "publish"):
                    s = await c.post(f"/v1/admin/changes/{change_id}/{step}", headers=headers)
                    assert s.status_code == 200, (step, s.text)
                assert s.json()["state"] == "published"

        _run(scenario())
        assert profile.dev_bindings is not None
        assert [str(b.id) for b in profile.dev_bindings.list_for_tenant(TENANT)] == [binding["id"]]
        assert profile.dev_bindings.list_for_tenant(uuid4()) == []

    def test_without_dev_state_dir_seams_stay_absent(self) -> None:
        profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})
        assert profile.dev_bindings is None
