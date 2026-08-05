"""PostgreSQL persistence adapters."""

from .ai import SQLAlchemyAITelemetryStore
from .booking import SQLAlchemyBookingStore
from .knowledge import SQLAlchemyKnowledgeStore
from .privacy import SQLAlchemyPrivacyStore
from .qualification import SQLAlchemyHandoffStore, SQLAlchemyQualificationStore
from .sqlalchemy.engine import create_engine, create_session_factory
from .sqlalchemy.unit_of_work import SQLAlchemyUnitOfWork
from .telegram import SQLAlchemyTelegramIdentityStore, SQLAlchemyTelegramUpdateStore

__all__ = [
    "SQLAlchemyAITelemetryStore",
    "SQLAlchemyBookingStore",
    "SQLAlchemyHandoffStore",
    "SQLAlchemyKnowledgeStore",
    "SQLAlchemyPrivacyStore",
    "SQLAlchemyQualificationStore",
    "SQLAlchemyTelegramIdentityStore",
    "SQLAlchemyTelegramUpdateStore",
    "SQLAlchemyUnitOfWork",
    "create_engine",
    "create_session_factory",
]
