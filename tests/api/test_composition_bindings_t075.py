"""Composition-root wiring tests for the ADR-0006/0007 bindings (T-IMPL-075).

Hermetic: ``environ`` is injected as a plain dict — no real environment
variables are read, no network client performs I/O (construction only).
What is verified is the WIRING policy:

- "not configured ⇒ binding absent" (the recorded composition-root DATA
  posture): missing bucket/addr returns None, callers keep in-memory.
- half-configuration is an ERROR, never a silent guess (20 §5).
- settings reprs never leak credentials (20 §5 — reprs get logged).
- builders produce the real adapter types bound to the configured targets.
"""

from __future__ import annotations

import pytest

from apps.composition import (
    ObjectStorageSettings,
    VaultSettings,
    build_object_storage,
    build_secret_manager,
    object_storage_settings_from_env,
    vault_settings_from_env,
)
from infrastructure.secrets import VaultSecretManager
from infrastructure.storage import S3ObjectStorage

ACCESS = "test-access-key-id"
SECRET = "test-secret-access-key-value"
TOKEN = "test-vault-token-value"


class TestObjectStorageSettings:
    def test_not_configured_returns_none(self) -> None:
        assert object_storage_settings_from_env({}) is None

    def test_blank_bucket_is_not_configured(self) -> None:
        assert object_storage_settings_from_env({"OBJECT_STORAGE_BUCKET": "  "}) is None

    def test_full_configuration_parsed(self) -> None:
        settings = object_storage_settings_from_env(
            {
                "OBJECT_STORAGE_BUCKET": "platform-blobs",
                "OBJECT_STORAGE_ENDPOINT": "http://minio.internal:9000",
                "OBJECT_STORAGE_ACCESS_KEY": ACCESS,
                "OBJECT_STORAGE_SECRET_KEY": SECRET,
                "OBJECT_STORAGE_REGION": "eu-central-1",
            }
        )
        assert settings == ObjectStorageSettings(
            bucket="platform-blobs",
            endpoint_url="http://minio.internal:9000",
            access_key=ACCESS,
            secret_key=SECRET,
            region="eu-central-1",
        )

    def test_ambient_credentials_allowed(self) -> None:
        # IAM-role deployments: bucket only, both keys absent.
        settings = object_storage_settings_from_env({"OBJECT_STORAGE_BUCKET": "platform-blobs"})
        assert settings is not None
        assert settings.access_key is None
        assert settings.secret_key is None
        assert settings.endpoint_url is None
        assert settings.region == "us-east-1"

    @pytest.mark.parametrize(
        "partial",
        [
            {"OBJECT_STORAGE_ACCESS_KEY": ACCESS},
            {"OBJECT_STORAGE_SECRET_KEY": SECRET},
        ],
    )
    def test_partial_credentials_error(self, partial: dict[str, str]) -> None:
        env = {"OBJECT_STORAGE_BUCKET": "b", **partial}
        with pytest.raises(ValueError, match="together"):
            object_storage_settings_from_env(env)

    def test_repr_never_contains_credentials(self) -> None:
        settings = object_storage_settings_from_env(
            {
                "OBJECT_STORAGE_BUCKET": "b",
                "OBJECT_STORAGE_ACCESS_KEY": ACCESS,
                "OBJECT_STORAGE_SECRET_KEY": SECRET,
            }
        )
        assert SECRET not in repr(settings)
        assert ACCESS not in repr(settings)

    def test_builder_returns_bound_adapter(self) -> None:
        # Construction only — boto3 clients are lazy, no I/O happens here.
        settings = ObjectStorageSettings(
            bucket="platform-blobs",
            endpoint_url="http://localhost:9000",
            access_key=ACCESS,
            secret_key=SECRET,
        )
        storage = build_object_storage(settings)
        assert isinstance(storage, S3ObjectStorage)


class TestVaultSettings:
    def test_not_configured_returns_none(self) -> None:
        assert vault_settings_from_env({}) is None

    def test_blank_addr_is_not_configured(self) -> None:
        assert vault_settings_from_env({"VAULT_ADDR": "  "}) is None

    def test_full_configuration_parsed(self) -> None:
        settings = vault_settings_from_env(
            {
                "VAULT_ADDR": "http://vault.internal:8200",
                "VAULT_TOKEN": TOKEN,
                "VAULT_MOUNT": "platform",
            }
        )
        assert settings == VaultSettings(
            address="http://vault.internal:8200",
            token=TOKEN,
            mount_point="platform",
        )

    def test_mount_defaults_to_secret(self) -> None:
        settings = vault_settings_from_env({"VAULT_ADDR": "http://v:8200", "VAULT_TOKEN": TOKEN})
        assert settings is not None
        assert settings.mount_point == "secret"

    def test_addr_without_token_error(self) -> None:
        with pytest.raises(ValueError, match="VAULT_TOKEN"):
            vault_settings_from_env({"VAULT_ADDR": "http://v:8200"})

    def test_repr_never_contains_token(self) -> None:
        settings = vault_settings_from_env({"VAULT_ADDR": "http://v:8200", "VAULT_TOKEN": TOKEN})
        assert TOKEN not in repr(settings)
        assert "[SCRUBBED]" in repr(settings)

    def test_builder_returns_bound_adapter(self) -> None:
        # Construction only — hvac clients are lazy, no I/O happens here.
        settings = VaultSettings(address="http://localhost:8200", token=TOKEN)
        manager = build_secret_manager(settings)
        assert isinstance(manager, VaultSecretManager)


class TestPostureCompleteness:
    def test_error_messages_never_contain_values(self) -> None:
        # Misconfiguration errors get logged — they must carry variable
        # NAMES only, never the provided values (20 §5).
        try:
            object_storage_settings_from_env(
                {"OBJECT_STORAGE_BUCKET": "b", "OBJECT_STORAGE_ACCESS_KEY": ACCESS}
            )
        except ValueError as error:
            assert ACCESS not in str(error)
