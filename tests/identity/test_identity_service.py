"""Auth + tenant-isolation tests for the identity service skeleton.

These are the MVP Phase 2 exit-criteria tests (41 §41):
"auth tests pass / tenant isolation tests pass".

Fakes only — no Argon2id, no real email delivery (forbidden this phase).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from core.contracts.identity import TenantStatus, TenantType, UserStatus
from core.identity import (
    AuthenticationFailed,
    InMemoryIdentityService,
    RegistrationError,
    SessionInvalid,
    VerificationFailed,
)

# --- fakes ---------------------------------------------------------------------


class FakeHasher:
    """Reversible fake hasher — test-only stand-in for the Argon2id binding."""

    def hash(self, password: str) -> str:
        return f"fakehash::{password[::-1]}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == self.hash(password)


class RecordingEmailSender:
    """Records (email, token) pairs instead of delivering anything."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_verification(self, email: str, token: str) -> None:
        self.sent.append((email, token))

    def last_token_for(self, email: str) -> str:
        for sent_email, token in reversed(self.sent):
            if sent_email == email:
                return token
        raise AssertionError(f"no verification sent to {email}")


@pytest.fixture()
def sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture()
def service(sender: RecordingEmailSender) -> InMemoryIdentityService:
    return InMemoryIdentityService(
        hasher=FakeHasher(), email_sender=sender, default_plan_id=uuid4()
    )


def _register_and_verify(
    service: InMemoryIdentityService,
    sender: RecordingEmailSender,
    email: str,
    password: str = "correct horse",
) -> None:
    service.register(email, password, "en")
    service.verify_email(sender.last_token_for(email))


# --- registration + personal tenant (41 §41) -----------------------------------


class TestRegistration:
    def test_register_creates_pending_unverified_user(
        self, service: InMemoryIdentityService
    ) -> None:
        user = service.register("A@Example.com", "pw12345678", "en")
        assert user.status is UserStatus.PENDING
        assert user.email_verified is False
        assert user.email == "a@example.com"  # normalized

    def test_register_creates_active_personal_tenant(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        user = service.register("a@example.com", "pw12345678", "en")
        _ = sender  # tenant readable only via an authorized session
        service.verify_email(sender.last_token_for("a@example.com"))
        session = service.login("a@example.com", "pw12345678")
        tenant = service.get_tenant(user.tenant_id, session_token=session.token)
        assert tenant.type is TenantType.PERSONAL
        assert tenant.status is TenantStatus.ACTIVE
        assert isinstance(tenant.plan_id, UUID)

    def test_register_sends_verification_token(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        assert len(sender.sent) == 1
        email, token = sender.sent[0]
        assert email == "a@example.com"
        assert len(token) >= 32  # opaque, unguessable

    def test_duplicate_email_rejected(self, service: InMemoryIdentityService) -> None:
        service.register("a@example.com", "pw12345678", "en")
        with pytest.raises(RegistrationError):
            service.register("A@EXAMPLE.COM", "other-pw-99", "en")

    def test_empty_email_or_password_rejected(self, service: InMemoryIdentityService) -> None:
        with pytest.raises(RegistrationError):
            service.register("  ", "pw12345678", "en")
        with pytest.raises(RegistrationError):
            service.register("a@example.com", "", "en")

    def test_no_plaintext_password_retained(self, service: InMemoryIdentityService) -> None:
        """20 §5: the service must keep only the opaque hash."""
        password = "super-secret-plaintext"
        service.register("a@example.com", password, "en")
        account = service._accounts_by_email["a@example.com"]
        assert password not in account.password_hash.replace(password[::-1], "")
        assert account.password_hash != password
        assert account.password_hash.startswith("fakehash::")


# --- email verification (41 §41, deny-by-default) --------------------------------


class TestEmailVerification:
    def test_verify_activates_user(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        user = service.verify_email(sender.last_token_for("a@example.com"))
        assert user.email_verified is True
        assert user.status is UserStatus.ACTIVE

    def test_token_is_single_use(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        token = sender.last_token_for("a@example.com")
        service.verify_email(token)
        with pytest.raises(VerificationFailed):
            service.verify_email(token)

    def test_unknown_token_rejected(self, service: InMemoryIdentityService) -> None:
        with pytest.raises(VerificationFailed):
            service.verify_email("not-a-real-token")

    def test_login_denied_before_verification(self, service: InMemoryIdentityService) -> None:
        """Deny-by-default: pending/unverified users cannot log in."""
        service.register("a@example.com", "pw12345678", "en")
        with pytest.raises(AuthenticationFailed):
            service.login("a@example.com", "pw12345678")


# --- login / session (41 §41 auth tests) -----------------------------------------


class TestLoginSession:
    def test_login_issues_opaque_session(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        assert len(session.token) >= 32
        resolved = service.resolve_session(session.token)
        assert resolved.user_id == session.user_id
        assert resolved.tenant_id == session.tenant_id

    def test_wrong_password_fails(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        with pytest.raises(AuthenticationFailed):
            service.login("a@example.com", "wrong password")

    def test_anti_enumeration_constant_failure(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        """Unknown email, wrong password, unverified account: identical error."""
        _register_and_verify(service, sender, "a@example.com")
        service.register("pending@example.com", "pw12345678", "en")

        messages = set()
        for email, pw in [
            ("nobody@example.com", "whatever"),  # unknown email
            ("a@example.com", "wrong password"),  # wrong password
            ("pending@example.com", "pw12345678"),  # unverified
        ]:
            with pytest.raises(AuthenticationFailed) as exc:
                service.login(email, pw)
            messages.add(str(exc.value))
        assert messages == {AuthenticationFailed.MESSAGE}

    def test_invalid_session_token_denied(self, service: InMemoryIdentityService) -> None:
        with pytest.raises(SessionInvalid):
            service.resolve_session("forged-token")

    def test_logout_revokes_session(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        service.logout(session.token)
        with pytest.raises(SessionInvalid):
            service.resolve_session(session.token)
        service.logout(session.token)  # idempotent

    def test_get_user_for_session(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        user = service.get_user_for_session(session.token)
        assert user.email == "a@example.com"
        assert user.tenant_id == session.tenant_id


# --- tenant isolation (41 §41 exit criterion; 20 §6) ------------------------------


class TestTenantIsolation:
    def test_each_registration_gets_distinct_tenant(self, service: InMemoryIdentityService) -> None:
        user_a = service.register("a@example.com", "pw12345678", "en")
        user_b = service.register("b@example.com", "pw12345678", "en")
        assert user_a.tenant_id != user_b.tenant_id

    def test_session_cannot_read_other_tenant(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        user_a = service.register("a@example.com", "pw12345678", "en")
        service.verify_email(sender.last_token_for("a@example.com"))
        _register_and_verify(service, sender, "b@example.com", "pw-b-123456")

        session_b = service.login("b@example.com", "pw-b-123456")
        with pytest.raises(SessionInvalid):
            service.get_tenant(user_a.tenant_id, session_token=session_b.token)

    def test_session_reads_own_tenant_only(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        user_a = service.register("a@example.com", "pw12345678", "en")
        service.verify_email(sender.last_token_for("a@example.com"))
        session_a = service.login("a@example.com", "pw12345678")
        tenant = service.get_tenant(user_a.tenant_id, session_token=session_a.token)
        assert tenant.id == user_a.tenant_id

    def test_session_is_tenant_bound(
        self, service: InMemoryIdentityService, sender: RecordingEmailSender
    ) -> None:
        """Every session resolves to exactly its user's tenant (20 §6)."""
        _register_and_verify(service, sender, "a@example.com")
        _register_and_verify(service, sender, "b@example.com")
        session_a = service.login("a@example.com", "correct horse")
        session_b = service.login("b@example.com", "correct horse")
        user_a = service.get_user_for_session(session_a.token)
        user_b = service.get_user_for_session(session_b.token)
        assert session_a.tenant_id == user_a.tenant_id
        assert session_b.tenant_id == user_b.tenant_id
        assert session_a.tenant_id != session_b.tenant_id
