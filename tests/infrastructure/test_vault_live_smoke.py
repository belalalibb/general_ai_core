"""Vault secret-manager LIVE smoke (ADR-0007 real-backend verification).

NOT part of the hermetic gates: every test here is SKIPPED unless
``VAULT_ADDR``/``VAULT_TOKEN`` point at a REAL Vault server with a KV v2
mount. Same posture as the provider live suites: skip-when-absent, never
fabricate a pass (41 §49). The token is read from env ONLY by the
composition wiring, never printed or embedded in artifacts (20 §5).

Run manually against a local dev Vault, e.g.:

    VAULT_ADDR=http://127.0.0.1:8200 VAULT_TOKEN=... \\
    python3 -m pytest tests/infrastructure/test_vault_live_smoke.py -v

Scope: the THIN slice the stubs cannot prove — real InvalidPath shapes,
real KV v2 version/metadata behaviour, real final deletion. Port
SEMANTICS are already proven hermetically (t074). Secrets written here
are uuid-tagged test values, revoked in-test (revocation IS the cleanup).
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from apps.composition import build_secret_manager, vault_settings_from_env
from core.secrets.errors import SecretNotFound
from infrastructure.secrets import VaultSecretManager

requires_live_vault = pytest.mark.skipif(
    not os.environ.get("VAULT_ADDR"),
    reason="VAULT_ADDR/VAULT_TOKEN not set — live Vault smoke runs manually only (41 §49)",
)

TENANT = uuid4()


@pytest.fixture()
def manager() -> VaultSecretManager:
    settings = vault_settings_from_env()
    assert settings is not None  # guarded by the skip marker
    return build_secret_manager(settings)


@requires_live_vault
class TestVaultLiveSmoke:
    def test_store_resolve_revoke_round_trip(
        self, manager: VaultSecretManager
    ) -> None:
        value = f"smoke-secret-{uuid4()}"
        ref = manager.store(TENANT, value)
        assert ref.startswith("vault:")
        assert manager.resolve(TENANT, ref) == value
        assert manager.exists(TENANT, ref) is True

        manager.revoke(TENANT, ref)  # revocation IS the cleanup
        assert manager.exists(TENANT, ref) is False
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT, ref)

    def test_real_invalid_path_shape_maps(self, manager: VaultSecretManager) -> None:
        # The REAL server's InvalidPath must map to SecretNotFound — exactly
        # what a stub cannot prove.
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT, f"vault:{uuid4()}")
        with pytest.raises(SecretNotFound):
            manager.revoke(TENANT, f"vault:{uuid4()}")

    def test_revocation_is_final_on_real_server(
        self, manager: VaultSecretManager
    ) -> None:
        # KV v2 soft-delete would leave the value recoverable; the adapter
        # uses metadata deletion — a re-read after revoke must be NOT FOUND,
        # not a "deleted version" response.
        ref = manager.store(TENANT, f"smoke-{uuid4()}")
        manager.revoke(TENANT, ref)
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT, ref)

    def test_foreign_tenant_isolation_on_real_server(
        self, manager: VaultSecretManager
    ) -> None:
        value = f"smoke-{uuid4()}"
        ref = manager.store(TENANT, value)
        try:
            with pytest.raises(SecretNotFound):
                manager.resolve(uuid4(), ref)
        finally:
            manager.revoke(TENANT, ref)  # cleanup
