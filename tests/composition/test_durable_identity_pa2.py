"""P-A.2 — DurableIdentityService port-parity tests.

Mirrors the PROVEN in-memory identity tests (tests/identity/
test_identity_service.py, the 41 §41 exit criteria) against the durable
binding, in two layers (41 §49):

1. Hermetic: a FAKE async identity repository (dict-backed, same
   semantics as ``PostgresIdentityRepository``) through the REAL
   AsyncBridge — proves the durable service reproduces every recorded
   policy decision (deny-by-default, anti-enumeration, single-use
   tokens, tenant isolation) plus the durability-specific facts: tokens
   at rest are DIGESTS only, restart ("new service instance, same
   repository") preserves sessions.
2. Live (env-gated, skip-when-absent): real Postgres round-trip proving
   registration → verification → login → restart → resolve_session
   against migration-0016 tables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from apps.composition.bridge import AsyncBridge
from apps.composition.identity import DurableIdentityService, _digest
from core.contracts.identity import (
    Tenant,
    TenantStatus,
    TenantType,
    User,
    UserStatus,
)
from core.identity import (
    AuthenticationFailed,
    IdentityServicePort,
    InMemoryIdentityService,
    RegistrationError,
    SessionInvalid,
    VerificationFailed,
)
from infrastructure.db.repositories.identity import (
    AccountRecord,
    SessionRecord,
)

# --- fakes (the recorded in-memory test fakes, verbatim shapes) -----------------


class FakeHasher:
    def hash(self, password: str) -> str:
        return f"fakehash::{password[::-1]}"

    def verify(self, password: str, hashed: str) -> bool:
        return hashed == self.hash(password)


class RecordingEmailSender:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_verification(self, email: str, token: str) -> None:
        self.sent.append((email, token))

    def last_token_for(self, email: str) -> str:
        for sent_email, token in reversed(self.sent):
            if sent_email == email:
                return token
        raise AssertionError(f"no verification sent to {email}")


@dataclass
class FakeIdentityRepository:
    """Dict-backed async repository — PostgresIdentityRepository semantics."""

    tenants: dict[UUID, Tenant] = field(default_factory=dict)
    users: dict[UUID, User] = field(default_factory=dict)
    credentials: dict[UUID, str] = field(default_factory=dict)
    verification_tokens: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, SessionRecord] = field(default_factory=dict)

    async def create_account(
        self,
        *,
        tenant: Tenant,
        user: User,
        password_hash: str,
        verification_token_sha256: str,
    ) -> None:
        self.tenants[tenant.id] = tenant
        self.users[user.id] = user
        self.credentials[user.id] = password_hash
        self.verification_tokens[verification_token_sha256] = user.email

    async def get_account_by_email(self, email: str) -> AccountRecord | None:
        for user in self.users.values():
            if user.email == email:
                return AccountRecord(
                    user=user, password_hash=self.credentials[user.id]
                )
        return None

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        return self.users.get(user_id)

    async def redeem_verification_token(
        self, token_sha256: str, *, now: datetime
    ) -> User | None:
        email = self.verification_tokens.pop(token_sha256, None)
        if email is None:
            return None
        for user_id, user in self.users.items():
            if user.email == email:
                updated = user.model_copy(
                    update={
                        "email_verified": True,
                        "status": UserStatus.ACTIVE,
                        "updated_at": now,
                    }
                )
                self.users[user_id] = updated
                return updated
        return None  # pragma: no cover - FK invariant

    async def save_session(self, record: SessionRecord) -> None:
        self.sessions[record.token_sha256] = record

    async def get_session(self, token_sha256: str) -> SessionRecord | None:
        return self.sessions.get(token_sha256)

    async def delete_session(self, token_sha256: str) -> None:
        self.sessions.pop(token_sha256, None)

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        return self.tenants.get(tenant_id)


@pytest.fixture()
def bridge():  # type: ignore[no-untyped-def]
    with AsyncBridge() as b:
        yield b


@pytest.fixture()
def sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture()
def repository() -> FakeIdentityRepository:
    return FakeIdentityRepository()


@pytest.fixture()
def service(
    bridge: AsyncBridge,
    sender: RecordingEmailSender,
    repository: FakeIdentityRepository,
) -> DurableIdentityService:
    return DurableIdentityService(
        hasher=FakeHasher(),
        email_sender=sender,
        default_plan_id=uuid4(),
        repository=repository,  # type: ignore[arg-type]  # structural twin
        bridge=bridge,
    )


def _register_and_verify(
    service: DurableIdentityService,
    sender: RecordingEmailSender,
    email: str,
    password: str = "correct horse",
) -> None:
    service.register(email, password, "en")
    service.verify_email(sender.last_token_for(email))


# --- port parity: the recorded 41 §41 policies, durable binding -----------------


class TestRegistrationParity:
    def test_register_creates_pending_unverified_user(
        self, service: DurableIdentityService
    ) -> None:
        user = service.register("A@Example.com", "pw12345678", "en")
        assert user.status is UserStatus.PENDING
        assert user.email_verified is False
        assert user.email == "a@example.com"  # normalized

    def test_register_creates_active_personal_tenant(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        user = service.register("a@example.com", "pw12345678", "en")
        service.verify_email(sender.last_token_for("a@example.com"))
        session = service.login("a@example.com", "pw12345678")
        tenant = service.get_tenant(user.tenant_id, session_token=session.token)
        assert tenant.type is TenantType.PERSONAL
        assert tenant.status is TenantStatus.ACTIVE

    def test_duplicate_email_rejected(
        self, service: DurableIdentityService
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        with pytest.raises(RegistrationError):
            service.register("A@EXAMPLE.COM", "other-pw-99", "en")

    def test_empty_email_or_password_rejected(
        self, service: DurableIdentityService
    ) -> None:
        with pytest.raises(RegistrationError):
            service.register("  ", "pw12345678", "en")
        with pytest.raises(RegistrationError):
            service.register("a@example.com", "", "en")

    def test_no_plaintext_password_at_rest(
        self, service: DurableIdentityService, repository: FakeIdentityRepository
    ) -> None:
        """20 §5 — durable rows carry only the opaque hash."""
        service.register("a@example.com", "supersecretpw", "en")
        stored = list(repository.credentials.values())
        assert stored and all("supersecretpw" not in value for value in stored)


class TestTokenDigestsAtRest:
    """The durability-specific 20 §5 facts — raw tokens never at rest."""

    def test_verification_token_stored_as_digest_only(
        self, service: DurableIdentityService,
        sender: RecordingEmailSender,
        repository: FakeIdentityRepository,
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        raw = sender.last_token_for("a@example.com")
        assert raw not in repository.verification_tokens
        assert _digest(raw) in repository.verification_tokens

    def test_session_token_stored_as_digest_only(
        self, service: DurableIdentityService,
        sender: RecordingEmailSender,
        repository: FakeIdentityRepository,
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        assert session.token not in repository.sessions
        assert _digest(session.token) in repository.sessions


class TestVerificationParity:
    def test_verify_activates_user(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        user = service.verify_email(sender.last_token_for("a@example.com"))
        assert user.status is UserStatus.ACTIVE
        assert user.email_verified is True

    def test_token_is_single_use(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        token = sender.last_token_for("a@example.com")
        service.verify_email(token)
        with pytest.raises(VerificationFailed):
            service.verify_email(token)

    def test_unknown_token_rejected(
        self, service: DurableIdentityService
    ) -> None:
        with pytest.raises(VerificationFailed):
            service.verify_email("no-such-token")


class TestLoginParity:
    def test_login_denied_before_verification(
        self, service: DurableIdentityService
    ) -> None:
        service.register("a@example.com", "pw12345678", "en")
        with pytest.raises(AuthenticationFailed):
            service.login("a@example.com", "pw12345678")

    def test_login_issues_opaque_session(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        assert len(session.token) >= 32
        resolved = service.resolve_session(session.token)
        assert resolved.user_id == session.user_id
        assert resolved.tenant_id == session.tenant_id

    def test_wrong_password_fails(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        with pytest.raises(AuthenticationFailed):
            service.login("a@example.com", "wrong")

    def test_anti_enumeration_constant_failure(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        """Unknown email and wrong password fail identically."""
        _register_and_verify(service, sender, "a@example.com")
        with pytest.raises(AuthenticationFailed) as unknown:
            service.login("nobody@example.com", "whatever")
        with pytest.raises(AuthenticationFailed) as wrong:
            service.login("a@example.com", "wrong")
        assert str(unknown.value) == str(wrong.value)

    def test_invalid_session_token_denied(
        self, service: DurableIdentityService
    ) -> None:
        with pytest.raises(SessionInvalid):
            service.resolve_session("forged-token")

    def test_logout_revokes_session(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        service.logout(session.token)
        with pytest.raises(SessionInvalid):
            service.resolve_session(session.token)
        service.logout(session.token)  # idempotent

    def test_get_user_for_session(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        _register_and_verify(service, sender, "a@example.com")
        session = service.login("a@example.com", "correct horse")
        user = service.get_user_for_session(session.token)
        assert user.email == "a@example.com"
        assert user.tenant_id == session.tenant_id


class TestTenantIsolationParity:
    def test_session_cannot_read_other_tenant(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        user_a = service.register("a@example.com", "pw-aaaaaa", "en")
        _ = user_a
        service.verify_email(sender.last_token_for("a@example.com"))
        user_b = service.register("b@example.com", "pw-bbbbbb", "en")
        service.verify_email(sender.last_token_for("b@example.com"))
        session_a = service.login("a@example.com", "pw-aaaaaa")
        with pytest.raises(SessionInvalid):
            service.get_tenant(user_b.tenant_id, session_token=session_a.token)

    def test_each_registration_gets_distinct_tenant(
        self, service: DurableIdentityService
    ) -> None:
        user_a = service.register("a@example.com", "pw-aaaaaa", "en")
        user_b = service.register("b@example.com", "pw-bbbbbb", "en")
        assert user_a.tenant_id != user_b.tenant_id


class TestRestartDurability:
    """THE P-A.2 acceptance: identity state outlives the 'process'."""

    def test_session_survives_restart(
        self,
        bridge: AsyncBridge,
        sender: RecordingEmailSender,
        repository: FakeIdentityRepository,
    ) -> None:
        plan = uuid4()
        first = DurableIdentityService(
            hasher=FakeHasher(),
            email_sender=sender,
            default_plan_id=plan,
            repository=repository,  # type: ignore[arg-type]
            bridge=bridge,
        )
        _register_and_verify(first, sender, "a@example.com")
        session = first.login("a@example.com", "correct horse")

        # "Restart": a brand-new service instance, same repository.
        second = DurableIdentityService(
            hasher=FakeHasher(),
            email_sender=RecordingEmailSender(),
            default_plan_id=plan,
            repository=repository,  # type: ignore[arg-type]
            bridge=bridge,
        )
        resolved = second.resolve_session(session.token)
        assert resolved.user_id == session.user_id
        user = second.get_user_for_session(session.token)
        assert user.email == "a@example.com"
        # And login still works post-restart (credential durability).
        assert second.login("a@example.com", "correct horse").token


class TestPortConformance:
    def test_both_services_satisfy_the_port(
        self, service: DurableIdentityService, sender: RecordingEmailSender
    ) -> None:
        durable: IdentityServicePort = service
        in_memory: IdentityServicePort = InMemoryIdentityService(
            hasher=FakeHasher(), email_sender=sender, default_plan_id=uuid4()
        )
        assert durable is not None and in_memory is not None


# --- Live layer (env-gated, skip-when-absent per 41 §49) ----------------------

requires_live_postgres = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — live Postgres tests run manually only (41 §49)",
)


@requires_live_postgres
class TestLiveIdentityDurability:
    def test_full_identity_lifecycle_survives_restart(self) -> None:
        from sqlalchemy import text

        from apps.composition.database import (
            build_database_bindings,
            database_settings_from_env,
        )
        from infrastructure.db.repositories.identity import (
            PostgresIdentityRepository,
        )
        from infrastructure.db.tables import metadata

        settings = database_settings_from_env()
        assert settings is not None
        email = f"live-{uuid4()}@example.test"
        plan_id = uuid4()

        with AsyncBridge() as bridge:
            bindings = build_database_bindings(settings)

            async def prepare() -> None:
                async with bindings.engine.begin() as conn:
                    await conn.run_sync(metadata.create_all)
                    await conn.execute(
                        text(
                            "INSERT INTO plans (id, name) VALUES (:id, :name)"
                            " ON CONFLICT (id) DO NOTHING"
                        ),
                        {"id": plan_id, "name": f"plan-{plan_id}"},
                    )

            sender = RecordingEmailSender()
            repo = PostgresIdentityRepository(bindings.session_factory)

            async def cleanup() -> None:
                async with bindings.engine.begin() as conn:
                    row = (
                        await conn.execute(
                            text(
                                "SELECT id, tenant_id FROM users"
                                " WHERE email = :email"
                            ),
                            {"email": email},
                        )
                    ).one_or_none()
                    if row is not None:
                        for stmt, params in (
                            (
                                "DELETE FROM sessions WHERE user_id = :uid",
                                {"uid": row.id},
                            ),
                            (
                                "DELETE FROM user_credentials"
                                " WHERE user_id = :uid",
                                {"uid": row.id},
                            ),
                            (
                                "DELETE FROM email_verification_tokens"
                                " WHERE email = :email",
                                {"email": email},
                            ),
                            (
                                "DELETE FROM users WHERE id = :uid",
                                {"uid": row.id},
                            ),
                            (
                                "DELETE FROM tenants WHERE id = :tid",
                                {"tid": row.tenant_id},
                            ),
                        ):
                            await conn.execute(text(stmt), params)
                await bindings.engine.dispose()

            bridge.run(prepare())
            try:
                first = DurableIdentityService(
                    hasher=FakeHasher(),
                    email_sender=sender,
                    default_plan_id=plan_id,
                    repository=repo,
                    bridge=bridge,
                )
                first.register(email, "live-password-1", "en")
                first.verify_email(sender.last_token_for(email))
                session = first.login(email, "live-password-1")

                # "Restart": new service instance over the same database.
                second = DurableIdentityService(
                    hasher=FakeHasher(),
                    email_sender=RecordingEmailSender(),
                    default_plan_id=plan_id,
                    repository=PostgresIdentityRepository(
                        bindings.session_factory
                    ),
                    bridge=bridge,
                )
                user = second.get_user_for_session(session.token)
                assert user.email == email
                assert user.status is UserStatus.ACTIVE
                second.logout(session.token)
                with pytest.raises(SessionInvalid):
                    second.resolve_session(session.token)
            finally:
                bridge.run(cleanup())
