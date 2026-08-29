"""HashiCorp Vault secret-manager binding (ADR-0007, ACCEPTED 2026-08-29).

Binds :class:`core.secrets.ports.SecretManagerPort` via hvac against
Vault's KV v2 secrets engine.

Spec anchors:

- 20 §5 (verbatim): secrets stored ONLY in a Secret Manager/KMS-backed
  system; the DB stores credential_ref only; no secrets in logs. This
  binding is that system's adapter.
- 20 §6 tenant scoping: every Vault path is ``{mount}/data/{tenant_id}/…``
  — the tenant segment is applied inside this adapter on EVERY operation,
  so a ref minted for one tenant can never resolve for another.
- Anti-enumeration (core/secrets/errors.py): unknown, foreign-tenant, and
  revoked refs all raise the same :class:`SecretNotFound`.

Ref model (the port's immutable-ref rotation contract):

- ``store()`` mints ``vault:{uuid4}`` and writes the value at
  ``{tenant_id}/{uuid}`` in the KV v2 mount. A NEW ref per store() call —
  rotation = store new + revoke old, exactly as the port records.
- ``revoke()`` uses KV v2 metadata deletion (destroys ALL versions) —
  revocation is final per the port contract; soft-delete would leave the
  value recoverable, violating "revocation is final".

Security posture (20 §5 — no secrets in logs):

- The secret value appears ONLY in the store() write payload and the
  resolve() return value. It is never embedded in exceptions, never
  logged, never included in any repr. Error paths carry the ref at most.
- Vault-side errors other than not-found propagate as-is: they originate
  from hvac/Vault and carry paths/refs, never values.

Design decisions (recorded here):

- The hvac CLIENT is injected, never constructed here: address/token/auth
  method (AppRole, k8s auth, …) are composition-root wiring (Lane C).
  This also keeps the binding hermetically testable against a stub.
- Malformed refs (not ``vault:`` + suffix) raise SecretNotFound without a
  network round-trip: they cannot have been minted by this adapter, and
  the anti-enumeration contract collapses "never existed" into the same
  error anyway.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import hvac
from hvac.exceptions import InvalidPath

from core.secrets.errors import SecretNotFound

_REF_PREFIX = "vault:"
_VALUE_FIELD = "value"


class VaultSecretManager:
    """Production ``SecretManagerPort`` binding (Vault KV v2 via hvac)."""

    def __init__(self, client: hvac.Client, mount_point: str = "secret") -> None:
        self._vault = client
        self._mount = mount_point

    @staticmethod
    def _path(tenant_id: UUID, credential_ref: str) -> str:
        """Vault path: tenant segment applied on EVERY operation (20 §6).

        Raises SecretNotFound for refs this adapter could not have minted
        (anti-enumeration: malformed == unknown).
        """
        if not credential_ref.startswith(_REF_PREFIX):
            raise SecretNotFound(credential_ref)
        suffix = credential_ref.removeprefix(_REF_PREFIX)
        if not suffix:
            raise SecretNotFound(credential_ref)
        return f"{tenant_id}/{suffix}"

    def store(self, tenant_id: UUID, secret_value: str) -> str:
        credential_ref = f"{_REF_PREFIX}{uuid4()}"
        self._vault.secrets.kv.v2.create_or_update_secret(
            path=self._path(tenant_id, credential_ref),
            secret={_VALUE_FIELD: secret_value},
            mount_point=self._mount,
        )
        return credential_ref

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        path = self._path(tenant_id, credential_ref)
        try:
            response: dict[str, Any] = self._vault.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self._mount, raise_on_deleted_version=True
            )
        except InvalidPath:
            raise SecretNotFound(credential_ref) from None
        data = response.get("data", {}).get("data", {})
        if _VALUE_FIELD not in data:
            raise SecretNotFound(credential_ref)
        value: str = data[_VALUE_FIELD]
        return value

    def revoke(self, tenant_id: UUID, credential_ref: str) -> None:
        path = self._path(tenant_id, credential_ref)
        # The port requires SecretNotFound for non-resolving refs, and KV v2
        # metadata deletion is a silent no-op for absent paths — so resolve
        # first (also collapses foreign/revoked/unknown into one error).
        self.resolve(tenant_id, credential_ref)
        # delete_metadata_and_all_versions: revocation is FINAL (port
        # contract) — soft delete would leave the value recoverable.
        self._vault.secrets.kv.v2.delete_metadata_and_all_versions(
            path=path, mount_point=self._mount
        )

    def exists(self, tenant_id: UUID, credential_ref: str) -> bool:
        try:
            self.resolve(tenant_id, credential_ref)
        except SecretNotFound:
            return False
        return True
