"""Secret-manager composition wiring (ADR-0007 binding at the root).

Environment contract (deployment surface — Lane C):

- ``VAULT_ADDR``   — REQUIRED. Vault server URL (standard Vault variable).
- ``VAULT_TOKEN``  — REQUIRED for token auth (the bootstrap credential).
                     Handed straight to hvac and NEVER logged (20 §5).
                     Non-token auth methods (AppRole, k8s) are a future
                     deployment decision — recorded open in ADR-0007's
                     consequence notes; the settings shape stays stable.
- ``VAULT_MOUNT``  — optional KV v2 mount point (default "secret").

"Not configured ⇒ absent": without VAULT_ADDR there is nothing to bind and
``vault_settings_from_env`` returns None — callers keep the in-memory
profile (dev/test, per ADR-0007; Alternative C remains REJECTED for
production, so a production deployment MUST set these).

ADDR without TOKEN is an ERROR, not a guess: a half-configured secret
manager must never fall back silently (20 §5 — custody is all-or-nothing).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import hvac

from infrastructure.secrets import VaultSecretManager

_ENV_ADDR = "VAULT_ADDR"
_ENV_TOKEN = "VAULT_TOKEN"  # noqa: S105 - env var NAME, not a credential
_ENV_MOUNT = "VAULT_MOUNT"


@dataclass(frozen=True, slots=True)
class VaultSettings:
    """Validated Vault deployment settings (no secrets in repr)."""

    address: str
    token: str
    mount_point: str = "secret"

    def __repr__(self) -> str:  # 20 §5: the token never appears in repr/logs
        return (
            f"VaultSettings(address={self.address!r}, "
            f"mount_point={self.mount_point!r}, token='[SCRUBBED]')"
        )


def vault_settings_from_env(
    environ: dict[str, str] | None = None,
) -> VaultSettings | None:
    """Read settings from the environment; None when not configured.

    ``environ`` is injectable for hermetic tests; production callers pass
    nothing and get ``os.environ``.
    """
    env = os.environ if environ is None else environ
    address = env.get(_ENV_ADDR, "").strip()
    if not address:
        return None  # not configured ⇒ binding absent (recorded posture)

    token = env.get(_ENV_TOKEN, "").strip()
    if not token:
        raise ValueError(
            "Secret manager misconfigured: VAULT_ADDR is set but VAULT_TOKEN "
            "is missing — a half-configured secret manager must never fall "
            "back silently (20 §5)."
        )

    return VaultSettings(
        address=address,
        token=token,
        mount_point=env.get(_ENV_MOUNT, "").strip() or "secret",
    )


def build_secret_manager(settings: VaultSettings) -> VaultSecretManager:
    """Construct the production binding from validated settings.

    The ONLY place an hvac client is created for the platform.
    """
    client = hvac.Client(url=settings.address, token=settings.token)
    return VaultSecretManager(client, mount_point=settings.mount_point)
