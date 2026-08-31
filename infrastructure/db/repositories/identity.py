"""PostgreSQL identity repository (P-A.2, migration 0016 + 0001 tables).

The durable state layer under the identity service semantics proven by
``core/identity/service.py`` (41 §41).  This repository is DUMB durable
truth: it stores/reads rows; ALL policy (deny-by-default login rules,
anti-enumeration, token generation, hashing) stays in the service layer
— the same split every V1 repository follows.

Security posture (20 §5, recorded in migration 0016):

- ``password_hash`` is the opaque PasswordHasherPort output — this
  module never sees a plaintext password.
- Session/verification tokens arrive here ALREADY DIGESTED (SHA-256 hex)
  — raw bearer tokens never reach the database layer.

Tenant isolation (20 §6): session rows denormalize tenant_id so one
read resolves the full (user_id, tenant_id) binding; user reads join
their stored tenant fact, never caller input.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.contracts.identity import (
    Tenant,
    TenantStatus,
    TenantType,
    User,
    UserStatus,
)
from infrastructure.db.tables import (
    email_verification_tokens,
    sessions,
    tenants,
    user_credentials,
    users,
)


@dataclass(frozen=True)
class AccountRecord:
    """One durable account: the user entity plus its credential hash."""

    user: User
    password_hash: str


@dataclass(frozen=True)
class SessionRecord:
    """One durable session row (token stored as digest only)."""

    token_sha256: str
    user_id: UUID
    tenant_id: UUID
    created_at: datetime


def _row_to_user(row: Any) -> User:
    return User(
        id=row.id,
        tenant_id=row.tenant_id,
        email=row.email,
        email_verified=row.email_verified,
        preferred_language=row.preferred_language,
        status=UserStatus(row.status),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _row_to_tenant(row: Any) -> Tenant:
    return Tenant(
        id=row.id,
        name=row.name,
        type=TenantType(row.type),
        status=TenantStatus(row.status),
        plan_id=row.plan_id,
    )


class PostgresIdentityRepository:
    """Async identity persistence over the 0001 + 0016 tables."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    # --- registration ------------------------------------------------------

    async def create_account(
        self,
        *,
        tenant: Tenant,
        user: User,
        password_hash: str,
        verification_token_sha256: str,
    ) -> None:
        """Persist tenant + user + credential + verification token — ONE tx.

        A partially-registered account must not exist (P6): either the
        whole registration lands or none of it does.
        """
        async with self._sessions() as session, session.begin():
            await session.execute(
                tenants.insert().values(
                    id=tenant.id,
                    name=tenant.name,
                    type=tenant.type.value,
                    status=tenant.status.value,
                    plan_id=tenant.plan_id,
                )
            )
            await session.execute(
                users.insert().values(
                    id=user.id,
                    tenant_id=user.tenant_id,
                    email=user.email,
                    email_verified=user.email_verified,
                    preferred_language=user.preferred_language,
                    status=user.status.value,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
            )
            await session.execute(
                user_credentials.insert().values(
                    user_id=user.id,
                    password_hash=password_hash,
                    updated_at=user.updated_at,
                )
            )
            await session.execute(
                email_verification_tokens.insert().values(
                    token_sha256=verification_token_sha256,
                    email=user.email,
                    created_at=user.created_at,
                )
            )

    async def get_account_by_email(self, email: str) -> AccountRecord | None:
        """The user + credential for ``email``, or None (service decides).

        None (not an exception): "unknown email" is a NORMAL branch of
        the anti-enumeration login flow — the service equalizes timing
        and raises its own constant failure.
        """
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(users, user_credentials.c.password_hash)
                    .join(user_credentials, user_credentials.c.user_id == users.c.id)
                    .where(users.c.email == email)
                )
            ).one_or_none()
        if row is None:
            return None
        return AccountRecord(user=_row_to_user(row), password_hash=row.password_hash)

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        async with self._sessions() as session:
            row = (
                await session.execute(select(users).where(users.c.id == user_id))
            ).one_or_none()
        return None if row is None else _row_to_user(row)

    # --- email verification -------------------------------------------------

    async def redeem_verification_token(
        self, token_sha256: str, *, now: datetime
    ) -> User | None:
        """Single-use redeem: DELETE the token + activate the user — ONE tx.

        Returns the activated user, or None when the token is unknown or
        already used (the service raises its named VerificationFailed).
        """
        async with self._sessions() as session, session.begin():
            deleted = (
                await session.execute(
                    delete(email_verification_tokens)
                    .where(email_verification_tokens.c.token_sha256 == token_sha256)
                    .returning(email_verification_tokens.c.email)
                )
            ).one_or_none()
            if deleted is None:
                return None
            await session.execute(
                users.update()
                .where(users.c.email == deleted.email)
                .values(
                    email_verified=True,
                    status=UserStatus.ACTIVE.value,
                    updated_at=now,
                )
            )
            row = (
                await session.execute(
                    select(users).where(users.c.email == deleted.email)
                )
            ).one()
        return _row_to_user(row)

    # --- sessions ------------------------------------------------------------

    async def save_session(self, record: SessionRecord) -> None:
        async with self._sessions() as session, session.begin():
            await session.execute(
                sessions.insert().values(
                    token_sha256=record.token_sha256,
                    user_id=record.user_id,
                    tenant_id=record.tenant_id,
                    created_at=record.created_at,
                )
            )

    async def get_session(self, token_sha256: str) -> SessionRecord | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(sessions).where(sessions.c.token_sha256 == token_sha256)
                )
            ).one_or_none()
        if row is None:
            return None
        return SessionRecord(
            token_sha256=row.token_sha256,
            user_id=row.user_id,
            tenant_id=row.tenant_id,
            created_at=row.created_at,
        )

    async def delete_session(self, token_sha256: str) -> None:
        """Revocation = row absence (idempotent, like the in-memory pop)."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                delete(sessions).where(sessions.c.token_sha256 == token_sha256)
            )

    # --- tenants ---------------------------------------------------------------

    async def get_tenant(self, tenant_id: UUID) -> Tenant | None:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(tenants).where(tenants.c.id == tenant_id)
                )
            ).one_or_none()
        return None if row is None else _row_to_tenant(row)
