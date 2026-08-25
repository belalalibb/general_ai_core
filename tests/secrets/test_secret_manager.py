"""Secret-manager port tests (MVP Phase 3, 41 §42; rules 20 §5/§6).

All secret values here are obviously-fake placeholders — no real secret
material is allowed anywhere in the repo (20 §5).
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from core.secrets import InMemorySecretManager, SecretManagerPort, SecretNotFound

TENANT_A = uuid4()
TENANT_B = uuid4()

FAKE_SECRET = "fake-placeholder-secret-value"  # noqa: S105 - obviously fake


@pytest.fixture()
def manager() -> InMemorySecretManager:
    return InMemorySecretManager()


class TestPortContract:
    def test_satisfies_port_protocol(self, manager: InMemorySecretManager) -> None:
        port: SecretManagerPort = manager
        assert isinstance(port, InMemorySecretManager)

    def test_store_resolve_round_trip(self, manager: InMemorySecretManager) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        assert manager.resolve(TENANT_A, ref) == FAKE_SECRET

    def test_ref_is_opaque_and_recognizable(
        self, manager: InMemorySecretManager
    ) -> None:
        """The ref never embeds the value and carries the credref_ marker."""
        ref = manager.store(TENANT_A, FAKE_SECRET)
        assert ref.startswith("credref_")
        assert FAKE_SECRET not in ref

    def test_each_store_mints_a_new_ref(self, manager: InMemorySecretManager) -> None:
        """Rotation model: refs are immutable handles, never reused."""
        ref1 = manager.store(TENANT_A, FAKE_SECRET)
        ref2 = manager.store(TENANT_A, FAKE_SECRET)
        assert ref1 != ref2

    def test_empty_secret_rejected(self, manager: InMemorySecretManager) -> None:
        with pytest.raises(ValueError):
            manager.store(TENANT_A, "")

    def test_unknown_ref_raises_not_found(
        self, manager: InMemorySecretManager
    ) -> None:
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_A, "credref_never-minted")

    def test_exists_reflects_lifecycle(self, manager: InMemorySecretManager) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        assert manager.exists(TENANT_A, ref) is True
        manager.revoke(TENANT_A, ref)
        assert manager.exists(TENANT_A, ref) is False


class TestRevocation:
    def test_revoked_ref_no_longer_resolves(
        self, manager: InMemorySecretManager
    ) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        manager.revoke(TENANT_A, ref)
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_A, ref)

    def test_revoke_unknown_ref_raises(self, manager: InMemorySecretManager) -> None:
        with pytest.raises(SecretNotFound):
            manager.revoke(TENANT_A, "credref_never-minted")

    def test_revoked_and_unknown_are_indistinguishable(
        self, manager: InMemorySecretManager
    ) -> None:
        """Anti-enumeration: revoked == never-existed to a resolver."""
        ref = manager.store(TENANT_A, FAKE_SECRET)
        manager.revoke(TENANT_A, ref)
        with pytest.raises(SecretNotFound) as revoked:
            manager.resolve(TENANT_A, ref)
        with pytest.raises(SecretNotFound) as unknown:
            manager.resolve(TENANT_A, "credref_never-minted")
        assert type(revoked.value) is type(unknown.value)


class TestNoLeak:
    """20 §5: no secrets in logs — nothing printable may carry the value."""

    def test_manager_repr_never_contains_secret(
        self, manager: InMemorySecretManager
    ) -> None:
        manager.store(TENANT_A, FAKE_SECRET)
        assert FAKE_SECRET not in repr(manager)
        assert FAKE_SECRET not in str(manager)

    def test_not_found_error_never_contains_secret(
        self, manager: InMemorySecretManager
    ) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        manager.revoke(TENANT_A, ref)
        with pytest.raises(SecretNotFound) as exc_info:
            manager.resolve(TENANT_A, ref)
        assert FAKE_SECRET not in str(exc_info.value)
        assert FAKE_SECRET not in repr(exc_info.value)


class TestTenantIsolation:
    """20 §6: a ref minted for tenant A never resolves for tenant B."""

    def test_foreign_tenant_cannot_resolve(
        self, manager: InMemorySecretManager
    ) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        with pytest.raises(SecretNotFound):
            manager.resolve(TENANT_B, ref)

    def test_foreign_tenant_cannot_revoke(
        self, manager: InMemorySecretManager
    ) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        with pytest.raises(SecretNotFound):
            manager.revoke(TENANT_B, ref)
        assert manager.resolve(TENANT_A, ref) == FAKE_SECRET

    def test_foreign_probe_indistinguishable_from_unknown(
        self, manager: InMemorySecretManager
    ) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        with pytest.raises(SecretNotFound) as foreign:
            manager.resolve(TENANT_B, ref)
        with pytest.raises(SecretNotFound) as unknown:
            manager.resolve(TENANT_B, "credref_never-minted")
        assert type(foreign.value) is type(unknown.value)

    def test_exists_is_tenant_scoped(self, manager: InMemorySecretManager) -> None:
        ref = manager.store(TENANT_A, FAKE_SECRET)
        assert manager.exists(TENANT_A, ref) is True
        assert manager.exists(TENANT_B, ref) is False
