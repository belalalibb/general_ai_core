"""Secret-manager port (dependency-inversion boundary; MVP Phase 3, 41 §42).

Spec anchors:

- 41 §42 deliverable: "secret manager abstraction".
- 20 §5 secrets rules (verbatim constraints this port enforces at the
  boundary): secrets stored only in a Secret Manager/KMS-backed system;
  DB stores credential_ref only; no secrets in logs.
- 40 §5.1: "metadata stores a credential_ref, the secret lives in the
  Secret Manager / KMS-backed system".
- 03 §4: ``Credential.credential_ref`` is the opaque reference this port
  mints and resolves.

Design decisions (recorded here):

- ``store()`` is the ONLY method that ever sees a secret value, and it
  immediately trades it for an opaque ``credential_ref``. Everything else
  in core (contracts, DB rows, logs, audit events) carries the ref only.
- ``resolve()`` is the ONLY method that returns a secret value, and it is
  meant to be called at the last possible moment by the adapter that needs
  it (provider binding, later phase) — never for storage or logging.
- ``tenant_id`` is explicit on every method; refs are tenant-scoped and a
  foreign tenant's ref resolves as if it did not exist (20 §6).
- There is deliberately NO list-values / dump / export operation on this
  port, and metadata operations never include the secret value.
- Rotation model: ``store()`` mints a NEW ref each time (refs are
  immutable handles); replacing a credential = store new + revoke old.
  This keeps audit trails unambiguous (which ref was used when).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class SecretManagerPort(Protocol):
    """Tenant-scoped secret custody behind opaque credential_ref handles.

    Implementations MUST guarantee: the secret value appears in no repr,
    no listing, no error message, and no metadata surface (20 §5); and a
    ref minted for one tenant never resolves for another (20 §6).
    """

    def store(self, tenant_id: UUID, secret_value: str) -> str:
        """Take custody of ``secret_value``; return a new opaque credential_ref.

        The caller must discard the plaintext immediately after this call.
        """
        ...

    def resolve(self, tenant_id: UUID, credential_ref: str) -> str:
        """Return the secret for ``credential_ref`` or raise SecretNotFound.

        Last-moment use only — the resolved value must never be stored,
        logged, or embedded in any contract object.
        """
        ...

    def revoke(self, tenant_id: UUID, credential_ref: str) -> None:
        """Destroy the secret behind ``credential_ref``; raise SecretNotFound
        if the ref does not resolve for this tenant. Revocation is final."""
        ...

    def exists(self, tenant_id: UUID, credential_ref: str) -> bool:
        """True iff ``credential_ref`` currently resolves for ``tenant_id``."""
        ...
