"""Phase 9 privacy composition using the PostgreSQL adapter."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.privacy import PrivacyApplication
from business_assistant.infrastructure.persistence import SQLAlchemyPrivacyStore
from business_assistant.infrastructure.system import UTCClock


def build_privacy_application(
    session_factory: async_sessionmaker[AsyncSession],
) -> PrivacyApplication:
    return PrivacyApplication(SQLAlchemyPrivacyStore(session_factory), UTCClock())
