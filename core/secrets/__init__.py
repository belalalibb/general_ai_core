"""Secret-manager abstraction (MVP Phase 3, 41 §42).

Public surface: the secret-manager port, its errors, and the in-memory
binding. Real KMS/vault bindings arrive in ``infrastructure/`` later behind
the same port; core only ever handles opaque ``credential_ref`` handles
(20 §5).
"""

from core.secrets.errors import SecretError, SecretNotFound
from core.secrets.memory import InMemorySecretManager
from core.secrets.ports import SecretManagerPort

__all__ = [
    "InMemorySecretManager",
    "SecretError",
    "SecretManagerPort",
    "SecretNotFound",
]
