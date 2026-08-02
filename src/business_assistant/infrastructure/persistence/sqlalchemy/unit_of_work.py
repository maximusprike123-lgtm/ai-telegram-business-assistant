"""One-session, one-transaction SQLAlchemy unit of work."""

from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from business_assistant.application.common.errors import IntegrityConflictError, StaleEntityError

from .repositories import (
    BookingRepository,
    CategoryRepository,
    ConversationRepository,
    CustomerRepository,
    HandoffRepository,
    KnowledgeRepository,
    LeadRepository,
    ScheduleRepository,
    ServiceRepository,
    TenantRepository,
)


class SQLAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        await self._session.begin()
        self.tenants = TenantRepository(self._session)
        self.customers = CustomerRepository(self._session)
        self.conversations = ConversationRepository(self._session)
        self.categories = CategoryRepository(self._session)
        self.services = ServiceRepository(self._session)
        self.schedules = ScheduleRepository(self._session)
        self.bookings = BookingRepository(self._session)
        self.leads = LeadRepository(self._session)
        self.handoffs = HandoffRepository(self._session)
        self.knowledge = KnowledgeRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Unit of work must be entered before use")
        return self._session

    async def commit(self) -> None:
        session = self._require_session()
        try:
            await session.commit()
        except StaleDataError as exc:
            raise StaleEntityError("aggregate") from exc
        except IntegrityError as exc:
            raise IntegrityConflictError("Committing transaction") from exc
        self._committed = True

    async def rollback(self) -> None:
        await self._require_session().rollback()
        self._committed = False
