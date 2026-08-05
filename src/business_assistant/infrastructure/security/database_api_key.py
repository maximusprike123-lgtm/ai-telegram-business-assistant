"""Database-backed tenant credential authentication with static-key compatibility."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import AuthenticationError
from business_assistant.application.common.security import Principal, Role
from business_assistant.domain.shared import TenantId
from business_assistant.infrastructure.persistence.sqlalchemy.models import (
    AdministrativeCredentialRow,
    TenantMemberRow,
)

from .api_key import StaticApiKeyAuthenticator
from .credentials import PBKDF2CredentialSecrets


class DatabaseApiKeyAuthenticator:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        secrets: PBKDF2CredentialSecrets,
        fallback: StaticApiKeyAuthenticator | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._secrets = secrets
        self._fallback = fallback
        self._dummy_hash = secrets.hash("invalid-credential")

    async def authenticate(self, provided_key: str | None) -> Principal:
        value = provided_key or ""
        prefix = value.split(".", 1)[0] if "." in value else ""
        if not prefix.startswith("atba_"):
            if self._fallback is not None:
                return await self._fallback.authenticate(provided_key)
            self._secrets.verify(value, self._dummy_hash)
            raise AuthenticationError()
        now = datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(AdministrativeCredentialRow, TenantMemberRow)
                .join(
                    TenantMemberRow,
                    (TenantMemberRow.tenant_id == AdministrativeCredentialRow.tenant_id)
                    & (TenantMemberRow.id == AdministrativeCredentialRow.member_id),
                )
                .where(AdministrativeCredentialRow.key_prefix == prefix)
                .with_for_update(of=AdministrativeCredentialRow)
            )
            pair = result.one_or_none()
            encoded = pair[0].secret_hash if pair is not None else self._dummy_hash
            verified = self._secrets.verify(value, encoded)
            if pair is None:
                raise AuthenticationError()
            credential, member = pair
            invalid = (
                not verified
                or credential.revoked_at is not None
                or (credential.expires_at is not None and credential.expires_at <= now)
                or not member.active
                or credential.role != member.role
            )
            if invalid:
                raise AuthenticationError()
            credential.last_used_at = now
            return Principal(
                member.subject,
                TenantId(credential.tenant_id),
                Role(member.role),
            )
