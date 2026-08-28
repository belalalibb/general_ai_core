"""Argon2id password-hashing binding tests (ADR-0005, T-IMPL-040).

Hermetic: Argon2 is local CPU work — a REAL binding is fully testable
without network (unlike provider credentials). Authority: 40 §5.2
(Argon2id / unique salt / strong policy), 20 §5 (no plaintext leaks),
core/identity/ports.py PasswordHasherPort (the bound contract).

Test-speed note: the low-cost parameters used in most tests exercise the
same code path as production defaults; ONE test runs the real defaults to
prove the production posture (kept single to bound gate time).
"""

from __future__ import annotations

from core.identity.ports import PasswordHasherPort
from core.identity.service import InMemoryIdentityService
from infrastructure.security.password import Argon2idPasswordHasher

# Low-cost parameters: same algorithm/code path, gate-friendly speed.
_FAST = {"time_cost": 1, "memory_cost": 8, "parallelism": 1}


def _fast_hasher() -> Argon2idPasswordHasher:
    return Argon2idPasswordHasher(**_FAST)


# --- Port conformance ---------------------------------------------------------------


def test_binding_satisfies_password_hasher_port() -> None:
    """Structural conformance to the core port (typed, not duck-hoped)."""
    hasher: PasswordHasherPort = _fast_hasher()
    assert hasher.verify("pw", hasher.hash("pw"))


def test_hash_verify_roundtrip_and_wrong_password_rejected() -> None:
    hasher = _fast_hasher()
    hashed = hasher.hash("correct horse battery staple")
    assert hasher.verify("correct horse battery staple", hashed) is True
    assert hasher.verify("correct horse battery stapl", hashed) is False
    assert hasher.verify("", hashed) is False


def test_production_defaults_produce_argon2id() -> None:
    """The DEFAULT construction (production posture) emits Argon2id PHC hashes."""
    hasher = Argon2idPasswordHasher()
    hashed = hasher.hash("pw")
    assert hashed.startswith("$argon2id$")
    assert hasher.verify("pw", hashed) is True


def test_unique_salt_same_password_different_hashes() -> None:
    """40 §5.2 'unique salt': two hashes of one password never collide."""
    hasher = _fast_hasher()
    first = hasher.hash("same password")
    second = hasher.hash("same password")
    assert first != second
    assert hasher.verify("same password", first)
    assert hasher.verify("same password", second)


def test_plaintext_never_appears_in_hash_output() -> None:
    """20 §5: the PHC string must not embed the password."""
    hasher = _fast_hasher()
    password = "S3cret-Plaintext-Marker"
    assert password not in hasher.hash(password)


# --- Failure honesty (no oracle, no exception crosses the port) ---------------------


def test_verify_returns_false_never_raises_for_garbage_hashes() -> None:
    hasher = _fast_hasher()
    for garbage in ("", "not-a-hash", "$argon2id$broken", "$2b$12$bcrypt-shaped"):
        assert hasher.verify("pw", garbage) is False


def test_verify_gives_no_cause_oracle() -> None:
    """Wrong password and malformed hash are indistinguishable (both False)."""
    hasher = _fast_hasher()
    hashed = hasher.hash("pw")
    wrong_password = hasher.verify("other", hashed)
    malformed_hash = hasher.verify("pw", "garbage")
    assert wrong_password is malformed_hash is False


# --- Rotation signal ----------------------------------------------------------------


def test_needs_rehash_false_for_current_policy_true_for_older() -> None:
    hasher = _fast_hasher()
    assert hasher.needs_rehash(hasher.hash("pw")) is False
    # A hash minted under a WEAKER policy must signal rotation under a stronger one.
    stronger = Argon2idPasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
    assert stronger.needs_rehash(hasher.hash("pw")) is True


def test_needs_rehash_true_for_malformed_hash() -> None:
    """Whatever produced a malformed hash is not current policy — rotate."""
    assert _fast_hasher().needs_rehash("garbage") is True


# --- Integration: the REAL identity service over the REAL binding -------------------


class _RecordingEmail:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_verification(self, email: str, token: str) -> None:
        self.sent.append((email, token))


def test_identity_service_full_flow_over_real_argon2id() -> None:
    """register → verify email → login works over the production binding,
    and the stored hash is opaque (no plaintext)."""
    from uuid import uuid4

    email_port = _RecordingEmail()
    service = InMemoryIdentityService(
        hasher=_fast_hasher(), email_sender=email_port, default_plan_id=uuid4()
    )
    user = service.register(
        email="a@example.com", password="pw-12345", preferred_language="en"
    )
    token = email_port.sent[0][1]
    service.verify_email(token)
    session = service.login(email="a@example.com", password="pw-12345")
    assert session.user_id == user.id
    # The service's stored account hash never contains the plaintext (20 §5).
    account = service._accounts_by_email["a@example.com"]  # test-only reach
    assert "pw-12345" not in account.password_hash
    assert account.password_hash.startswith("$argon2id$")
