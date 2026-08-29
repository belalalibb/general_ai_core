"""Vault secret-manager binding tests (ADR-0007, T-IMPL-074).

Hermetic posture (recorded in ADR-0007): a real Vault needs a SERVER, so
the hermetic suite drives the binding against an in-process stub speaking
the exact hvac KV v2 surface the adapter uses (create_or_update_secret /
read_secret_version / delete_metadata_and_all_versions + InvalidPath).
What is verified here is the ADAPTER's mapping logic: tenant-segmented
paths, opaque-ref minting, anti-enumeration collapse, final revocation,
and the 20 §5 no-value-on-error-paths guarantee. Real-backend smoke tests
live OUTSIDE hermetic gates per ADR-0002/0003 posture.

Authority: core/secrets/ports.py (bound contract), 20 §5/§6,
tests/secrets/test_secret_manager.py (the port-semantics suite the
in-memory implementation passes — mirrored where meaningful).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from hvac.exceptions import InvalidPath

from core.secrets.errors import SecretNotFound
from core.secrets.ports import SecretManagerPort
from infrastructure.secrets import VaultSecretManager

TENANT_A = UUID("00000000-0000-0000-0000-00000000000a")
TENANT_B = UUID("00000000-0000-0000-0000-00000000000b")

SECRET = "sk-live-EXAMPLE-not-a-real-key"


class StubKvV2:
    """In-process double for the exact hvac KV v2 surface the adapter uses."""

    def __init__(self) -> None:
        self.paths: dict[tuple[str, str], dict[str, str]] = {}

    def create_or_update_secret(
        self, *, path: str, secret: dict[str, str], mount_point: str
    ) -> dict[str, Any]:
        self.paths[(mount_point, path)] = dict(secret)
        return {}

    def read_secret_version(
        self, *, path: str, mount_point: str, raise_on_deleted_version: bool
    ) -> dict[str, Any]:
        try:
            data = self.paths[(mount_point, path)]
        except KeyError:
            raise InvalidPath(f"no value at {mount_point}/data/{path}") from None
        return {"data": {"data": dict(data)}}

    def delete_metadata_and_all_versions(
        self, *, path: str, mount_point: str
    ) -> dict[str, Any]:
        # Faithful to Vault: silent no-op for absent paths.
        self.paths.pop((mount_point, path), None)
        return {}


def _client(kv: StubKvV2) -> Any:
    return SimpleNamespace(secrets=SimpleNamespace(kv=SimpleNamespace(v2=kv)))


@pytest.fixture()
def kv() -> StubKvV2:
    return StubKvV2()


@pytest.fixture()
def manager(kv: StubKvV2) -> VaultSecretManager:
    return VaultSecretManager(_client(kv), mount_point="secret")


class TestPortConformance:
    def test_satisfies_port_protocol(self, manager: VaultSecretManager) -> None:
        port: SecretManagerPort = manager
        assert port is manager

    def test_store_resolve_round_trip(self, manager: VaultSecretManager) -> None:
        ref = manager.store(TENANT_A, SECRET)
        assert manager.resolve(TENANT_A, ref) == SECRET

    def test_ref_is_opaque_and_recognizable(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        assert ref.startswith("vault:")
        assert SECRET not in ref
        assert str(TENANT_A) not in ref  # tenancy lives in the PATH, not the ref

    def test_each_store_mints_a_new_ref(self, manager: VaultSecretManager) -> None:
        first = manager.store(TENANT_A, SECRET)
        second = manager.store(TENANT_A, SECRET)
        assert first != second
        assert manager.resolve(TENANT_A, first) == SECRET
        assert manager.resolve(TENANT_A, second) == SECRET

    def test_unknown_ref_raises_not_found(self, manager: VaultSecretManager) -> None:
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_A, "vault:never-minted")

    def test_malformed_ref_raises_not_found_without_backend_call(
        self, kv: StubKvV2
    ) -> None:
        class Exploding(StubKvV2):
            def read_secret_version(self, **kwargs: Any) -> dict[str, Any]:
                raise AssertionError("backend must not be called for malformed refs")

        manager = VaultSecretManager(_client(Exploding()), mount_point="secret")
        for bad in ("", "vault:", "not-a-ref", "s3:whatever"):
            with pytest.raises(SecretNotFound):
                manager.resolve(TENANT_A, bad)

    def test_exists_reflects_lifecycle(self, manager: VaultSecretManager) -> None:
        ref = manager.store(TENANT_A, SECRET)
        assert manager.exists(TENANT_A, ref) is True
        manager.revoke(TENANT_A, ref)
        assert manager.exists(TENANT_A, ref) is False

    def test_revoked_ref_no_longer_resolves(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        manager.revoke(TENANT_A, ref)
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_A, ref)

    def test_revocation_destroys_all_versions(
        self, manager: VaultSecretManager, kv: StubKvV2
    ) -> None:
        # Final revocation = metadata deletion: nothing remains at the path.
        ref = manager.store(TENANT_A, SECRET)
        manager.revoke(TENANT_A, ref)
        assert kv.paths == {}

    def test_revoke_unknown_ref_raises(self, manager: VaultSecretManager) -> None:
        # Vault's delete is silently idempotent; the ADAPTER must still
        # honour the port's SecretNotFound contract.
        with pytest.raises(SecretNotFound):
            manager.revoke(TENANT_A, "vault:never-minted")

    def test_revoked_and_unknown_are_indistinguishable(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        manager.revoke(TENANT_A, ref)
        with pytest.raises(SecretNotFound) as revoked:
            manager.resolve(TENANT_A, ref)
        with pytest.raises(SecretNotFound) as unknown:
            manager.resolve(TENANT_A, "vault:never-minted")
        assert type(revoked.value) is type(unknown.value)


class TestNoSecretLeakage:
    def test_not_found_error_never_contains_secret(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        manager.revoke(TENANT_A, ref)
        try:
            manager.resolve(TENANT_A, ref)
        except SecretNotFound as error:
            assert SECRET not in repr(error)
            assert SECRET not in str(error)

    def test_manager_repr_never_contains_secret(
        self, manager: VaultSecretManager
    ) -> None:
        manager.store(TENANT_A, SECRET)
        assert SECRET not in repr(manager)

    def test_vault_path_never_contains_secret(
        self, manager: VaultSecretManager, kv: StubKvV2
    ) -> None:
        manager.store(TENANT_A, SECRET)
        for _, path in kv.paths:
            assert SECRET not in path


class TestTenantIsolation:
    def test_paths_are_tenant_segmented(
        self, manager: VaultSecretManager, kv: StubKvV2
    ) -> None:
        # The 20 §6 mechanism itself: every physical path carries the tenant.
        manager.store(TENANT_A, "a-secret")
        manager.store(TENANT_B, "b-secret")
        prefixes = {path.split("/")[0] for _, path in kv.paths}
        assert prefixes == {str(TENANT_A), str(TENANT_B)}

    def test_foreign_tenant_cannot_resolve(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_B, ref)

    def test_foreign_tenant_cannot_revoke(self, manager: VaultSecretManager) -> None:
        ref = manager.store(TENANT_A, SECRET)
        with pytest.raises(SecretNotFound):
            manager.revoke(TENANT_B, ref)
        assert manager.resolve(TENANT_A, ref) == SECRET  # custody intact

    def test_foreign_probe_indistinguishable_from_unknown(
        self, manager: VaultSecretManager
    ) -> None:
        ref = manager.store(TENANT_A, SECRET)
        with pytest.raises(SecretNotFound) as foreign:
            manager.resolve(TENANT_B, ref)
        with pytest.raises(SecretNotFound) as unknown:
            manager.resolve(TENANT_B, "vault:never-minted")
        assert type(foreign.value) is type(unknown.value)

    def test_exists_is_tenant_scoped(self, manager: VaultSecretManager) -> None:
        ref = manager.store(TENANT_A, SECRET)
        assert manager.exists(TENANT_A, ref) is True
        assert manager.exists(TENANT_B, ref) is False
