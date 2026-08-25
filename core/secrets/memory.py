"""In-memory secret manager (MVP Phase 3 skeleton binding, 41 §42).

Satisfies :class:`~core.secrets.ports.SecretManagerPort` against process
memory — same skeleton discipline as the Phase 2/3 in-memory bindings.
Real KMS/vault custody arrives later behind the same port.

Leak-resistance mechanics (20 §5), even in a test-only binding:

- ``repr``/``str`` of the manager never include secret values (guarded by
  an explicit ``__repr__`` and asserted by tests).
- refs are unguessable opaque tokens (``secrets.token_urlsafe``), prefixed
  ``credref_`` so accidental logging of a ref is recognizable AND safe.
- revocation removes the value from the mapping entirely.
"""

from __future__ import annotations

import secrets as _secrets
from uuid import UUID

from core.secrets.errors import SecretNotFound


def _new_credential_ref() -> str:
    """Opaque, unguessable, recognizable credential reference."""
    return f"credref_{_secrets.token_urlsafe(24)}"


class InMemorySecretManager:
    """Process-memory implementation of ``SecretManagerPort``."""

    def __init__(self) -> None:
        self._secrets: dict[tuple[UUID, str], str] = {}

    def store(self, tenant_id: UUID, secret_value: str) -> str:
        if not secret_value:
            raise ValueError("secret_value must be non-empty")
        ref = _new_credential_ref()
        self._secrets[(tenant_id, ref)] = secret_value
        return ref

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        try:
            return self._secrets[(tenant_id, credential_ref)]
        except KeyError:
            raise SecretNotFound(credential_ref) from None

    def revoke(self, tenant_id: UUID, credential_ref: str) -> None:
        if self._secrets.pop((tenant_id, credential_ref), None) is None:
            raise SecretNotFound(credential_ref)

    def exists(self, tenant_id: UUID, credential_ref: str) -> bool:
        return (tenant_id, credential_ref) in self._secrets

    def __repr__(self) -> str:  # pragma: no cover - trivial
        """Never reveal values (20 §5: no secrets in logs/reprs)."""
        return f"<InMemorySecretManager refs={len(self._secrets)}>"
