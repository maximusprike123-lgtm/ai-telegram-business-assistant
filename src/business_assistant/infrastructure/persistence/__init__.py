"""PostgreSQL persistence adapters."""

from .administration import SQLAlchemyTenantAccessPolicy, SQLAlchemyTenantAdministrationStore
from .ai import SQLAlchemyAITelemetryStore
from .background import SQLAlchemyBackgroundStore
from .booking import SQLAlchemyBookingStore
from .knowledge import SQLAlchemyKnowledgeStore
from .privacy import SQLAlchemyPrivacyStore
from .qualification import SQLAlchemyHandoffStore, SQLAlchemyQualificationStore
from .sqlalchemy.engine import create_engine, create_session_factory
from .sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork
from .telegram import SQLAlchemyTelegramIdentityStore, SQLAlchemyTelegramUpdateStore

__all__ = [
    "SQLAlchemyAITelemetryStore",
    "SQLAlchemyBackgroundStore",
    "SQLAlchemyBookingStore",
    "SQLAlchemyHandoffStore",
    "SQLAlchemyKnowledgeStore",
    "SQLAlchemyPrivacyStore",
    "SQLAlchemyQualificationStore",
    "SQLAlchemyTelegramIdentityStore",
    "SQLAlchemyTelegramUpdateStore",
    "SQLAlchemyTenantAccessPolicy",
    "SQLAlchemyTenantAdministrationStore",
    "SQLAlchemyUnitOfWork",
    "create_engine",
    "create_session_factory",
]
