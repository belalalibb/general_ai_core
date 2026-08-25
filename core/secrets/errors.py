"""Secret-manager errors (closed, minimal set for the MVP port).

Error messages carry the credential_ref at most — NEVER a secret value
(20 §5: no secrets in logs; errors get logged).

Anti-enumeration (mirrors ``core.storage``): an unknown ref, a foreign
tenant's ref, and a revoked ref all raise the same
:class:`SecretNotFound` — resolvers must not be able to distinguish
"never existed" from "exists elsewhere" from "revoked" (20 §6).
"""

from __future__ import annotations


class SecretError(Exception):
    """Base class for secret-manager failures."""


class SecretNotFound(SecretError):
    """No resolvable secret for this credential_ref in the caller's tenant.

    Raised identically for unknown refs, foreign-tenant refs, and revoked
    refs (anti-enumeration; 20 §5/§6).
    """
