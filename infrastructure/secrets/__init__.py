"""Secret-manager infrastructure bindings (ADR-0007: HashiCorp Vault via hvac)."""

from infrastructure.secrets.vault import VaultSecretManager

__all__ = ["VaultSecretManager"]
