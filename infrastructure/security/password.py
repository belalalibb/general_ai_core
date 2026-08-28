"""Argon2id password-hashing binding (ADR-0005, ACCEPTED 2026-08-28).

Binds :class:`core.identity.ports.PasswordHasherPort` via ``argon2-cffi``'s
``PasswordHasher`` — the production implementation the port docstring
mandates ("Production binding must be Argon2id").

Spec anchors:

- 40 §5.2 Authentication Baseline (verbatim): "Password = Argon2id, unique
  salt, strong policy, compromised-password checks".
  - Argon2id: argon2-cffi's ``PasswordHasher`` uses type ID by default.
  - Unique salt: the library generates a fresh random salt per ``hash()``
    call (encoded into the PHC string) — never caller-supplied here.
  - Strong policy: library defaults track RFC 9106 recommendations;
    parameters are overridable ONLY at the composition root via the
    constructor (no hardcoded weakening anywhere).
  - Compromised-password checks: OUT OF SCOPE of this binding (separate
    data-source decision — recorded OPEN in ADR-0005 and the state file).
- 20 §5: plaintext never stored/logged. This binding returns/accepts only
  the opaque PHC-format hash; it never logs, and exceptions raised by the
  library are caught so password material can never ride an error path.

Port-contract honesty:

- ``verify()`` returns False for ANY non-match reason (wrong password,
  malformed/foreign hash, wrong parameters) — the port's boolean contract
  gives the caller no oracle about WHY (anti-enumeration posture upstream
  relies on this).
- ``needs_rehash()`` is an EXTRA capability beyond the port (policy
  rotation support per ADR-0005); callers that only know the port simply
  never call it.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2idPasswordHasher:
    """Production ``PasswordHasherPort`` binding (Argon2id via argon2-cffi).

    Parameters mirror ``argon2.PasswordHasher`` and default to the library's
    RFC 9106-tracking defaults. Override ONLY at the composition root.
    """

    def __init__(
        self,
        *,
        time_cost: int | None = None,
        memory_cost: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        defaults = PasswordHasher()
        self._hasher = PasswordHasher(
            time_cost=time_cost if time_cost is not None else defaults.time_cost,
            memory_cost=memory_cost if memory_cost is not None else defaults.memory_cost,
            parallelism=parallelism if parallelism is not None else defaults.parallelism,
        )

    def hash(self, password: str) -> str:
        """Return an opaque PHC-format Argon2id hash (fresh salt per call)."""
        return self._hasher.hash(password)

    def verify(self, password: str, hashed: str) -> bool:
        """True iff ``password`` matches ``hashed``; False for ANY failure.

        Mismatch, malformed hash, and foreign-algorithm hashes all collapse
        into False — no exception crosses the port boundary, so no error
        path can carry password material or a failure-cause oracle.
        """
        try:
            return self._hasher.verify(hashed, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, hashed: str) -> bool:
        """True if ``hashed`` predates current policy (rotation signal).

        Malformed/foreign hashes are True: whatever produced them is not
        the current policy, and the rotation path (re-hash on next
        successful login) is the safe answer.
        """
        try:
            return self._hasher.check_needs_rehash(hashed)
        except InvalidHashError:
            return True
