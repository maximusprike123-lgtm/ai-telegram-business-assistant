"""Tenant-scoped SQLAlchemy repository implementations."""

from collections.abc import Callable, Sequence
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from business_assistant.application.common.errors import (
    DuplicateEntityError,
    IntegrityConflictError,
)
from business_assistant.domain.bookings import Booking
from business_assistant.domain.catalog import Service, ServiceCategory
from business_assistant.domain.conversations import Conversation
from business_assistant.domain.customers import Customer
from business_assistant.domain.handoffs import HandoffCase
from business_assistant.domain.knowledge import KnowledgeDocument
from business_assistant.domain.leads import Lead
from business_assistant.domain.scheduling import BusinessSchedule
from business_assistant.domain.shared import (
    BookingId,
    CategoryId,
    ConversationId,
    CustomerId,
    DocumentId,
    EntityId,
    HandoffId,
    LeadId,
    ScheduleId,
    ServiceId,
    TenantId,
    TenantMismatchError,
)
from business_assistant.domain.tenants import Tenant, TenantPublicProfile

from .base import Base
from .mappers import (
    booking_from_row,
    booking_to_row,
    category_from_row,
    category_to_row,
    conversation_from_row,
    conversation_to_row,
    customer_from_row,
    customer_to_row,
    handoff_from_row,
    handoff_to_row,
    knowledge_from_row,
    knowledge_to_row,
    lead_from_row,
    lead_to_row,
    public_profile_from_row,
    public_profile_to_row,
    schedule_from_rows,
    schedule_to_rows,
    service_from_row,
    service_to_row,
    tenant_from_row,
    tenant_to_row,
)
from .models import (
    BookingRow,
    BookingStatusHistoryRow,
    BusinessScheduleRow,
    ConversationRow,
    CustomerRow,
    HandoffCaseRow,
    KnowledgeDocumentRow,
    LeadRow,
    ScheduleIntervalRow,
    ScheduleOverrideRow,
    ServiceCategoryRow,
    ServiceRow,
    TenantPublicProfileRow,
    TenantRow,
)

EntityT = TypeVar("EntityT")
IdT = TypeVar("IdT", bound=EntityId)
RowT = TypeVar("RowT", bound=Base)


def _page_limit(limit: int) -> int:
    if not 1 <= limit <= 100:
        raise ValueError("Repository page limit must be between 1 and 100")
    return limit


def _cursor(cursor: str | None) -> UUID | None:
    return UUID(cursor) if cursor is not None else None


async def _flush(session: AsyncSession, entity_name: str) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23505":
            raise DuplicateEntityError(entity_name) from exc
        raise IntegrityConflictError(f"Persisting {entity_name}") from exc


class SQLAlchemyRepository(Generic[EntityT, IdT, RowT]):  # noqa: UP046
    def __init__(
        self,
        session: AsyncSession,
        row_type: type[RowT],
        to_row: Callable[[EntityT], RowT],
        from_row: Callable[[RowT], EntityT],
        entity_name: str,
    ) -> None:
        self._session = session
        self._row_type = row_type
        self._to_row = to_row
        self._from_row = from_row
        self._entity_name = entity_name

    async def get(self, tenant_id: TenantId, entity_id: IdT) -> EntityT | None:
        row = await self._session.scalar(
            select(self._row_type).where(
                self._row_type.tenant_id == tenant_id.value,  # type: ignore[attr-defined]
                self._row_type.id == entity_id.value,  # type: ignore[attr-defined]
            )
        )
        return self._from_row(row) if row is not None else None

    async def add(self, tenant_id: TenantId, entity: EntityT) -> None:
        entity_tenant_id = getattr(entity, "tenant_id", None)
        if entity_tenant_id != tenant_id:
            raise TenantMismatchError(self._entity_name)
        self._session.add(self._to_row(entity))
        await _flush(self._session, self._entity_name)

    async def list_page(
        self, tenant_id: TenantId, *, cursor: str | None, limit: int
    ) -> Sequence[EntityT]:
        statement = select(self._row_type).where(
            self._row_type.tenant_id == tenant_id.value  # type: ignore[attr-defined]
        )
        parsed_cursor = _cursor(cursor)
        if parsed_cursor is not None:
            statement = statement.where(
                self._row_type.id > parsed_cursor  # type: ignore[attr-defined]
            )
        rows = (
            await self._session.scalars(
                statement.order_by(
                    self._row_type.id  # type: ignore[attr-defined]
                ).limit(_page_limit(limit))
            )
        ).all()
        return [self._from_row(row) for row in rows]


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, entity_id: TenantId) -> Tenant | None:
        if tenant_id != entity_id:
            return None
        row = await self._session.get(TenantRow, entity_id.value)
        return tenant_from_row(row) if row is not None else None

    async def add(self, tenant_id: TenantId, entity: Tenant) -> None:
        if entity.id != tenant_id:
            raise TenantMismatchError("Tenant")
        self._session.add(tenant_to_row(entity))
        await _flush(self._session, "Tenant")

    async def list_page(
        self, tenant_id: TenantId, *, cursor: str | None, limit: int
    ) -> Sequence[Tenant]:
        row = await self.get(tenant_id, tenant_id)
        return [row] if row is not None and _page_limit(limit) else []


class CustomerRepository(SQLAlchemyRepository[Customer, CustomerId, CustomerRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, CustomerRow, customer_to_row, customer_from_row, "Customer")


class ConversationRepository(SQLAlchemyRepository[Conversation, ConversationId, ConversationRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session, ConversationRow, conversation_to_row, conversation_from_row, "Conversation"
        )


class CategoryRepository(SQLAlchemyRepository[ServiceCategory, CategoryId, ServiceCategoryRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session, ServiceCategoryRow, category_to_row, category_from_row, "ServiceCategory"
        )

    async def list_active(self, tenant_id: TenantId) -> Sequence[ServiceCategory]:
        rows = (
            await self._session.scalars(
                select(ServiceCategoryRow)
                .where(
                    ServiceCategoryRow.tenant_id == tenant_id.value,
                    ServiceCategoryRow.active.is_(True),
                )
                .order_by(ServiceCategoryRow.sort_order, ServiceCategoryRow.id)
            )
        ).all()
        return [category_from_row(row) for row in rows]

    async def get_active(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> ServiceCategory | None:
        row = await self._session.scalar(
            select(ServiceCategoryRow).where(
                ServiceCategoryRow.tenant_id == tenant_id.value,
                ServiceCategoryRow.id == category_id.value,
                ServiceCategoryRow.active.is_(True),
            )
        )
        return category_from_row(row) if row is not None else None


class ServiceRepository(SQLAlchemyRepository[Service, ServiceId, ServiceRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ServiceRow, service_to_row, service_from_row, "Service")

    async def list_active(
        self, tenant_id: TenantId, *, category_id: CategoryId | None
    ) -> Sequence[Service]:
        statement = (
            select(ServiceRow)
            .join(
                ServiceCategoryRow,
                (ServiceCategoryRow.tenant_id == ServiceRow.tenant_id)
                & (ServiceCategoryRow.id == ServiceRow.category_id),
            )
            .where(
                ServiceRow.tenant_id == tenant_id.value,
                ServiceRow.active.is_(True),
                ServiceCategoryRow.active.is_(True),
            )
        )
        if category_id is not None:
            statement = statement.where(ServiceRow.category_id == category_id.value)
        rows = (
            await self._session.scalars(statement.order_by(ServiceRow.code, ServiceRow.id))
        ).all()
        return [service_from_row(row) for row in rows]

    async def get_active(self, tenant_id: TenantId, service_id: ServiceId) -> Service | None:
        row = await self._session.scalar(
            select(ServiceRow)
            .join(
                ServiceCategoryRow,
                (ServiceCategoryRow.tenant_id == ServiceRow.tenant_id)
                & (ServiceCategoryRow.id == ServiceRow.category_id),
            )
            .where(
                ServiceRow.tenant_id == tenant_id.value,
                ServiceRow.id == service_id.value,
                ServiceRow.active.is_(True),
                ServiceCategoryRow.active.is_(True),
            )
        )
        return service_from_row(row) if row is not None else None


class PublicProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId) -> TenantPublicProfile | None:
        row = await self._session.scalar(
            select(TenantPublicProfileRow).where(
                TenantPublicProfileRow.tenant_id == tenant_id.value
            )
        )
        return public_profile_from_row(row) if row is not None else None

    async def upsert(self, tenant_id: TenantId, entity: TenantPublicProfile) -> None:
        if entity.tenant_id != tenant_id:
            raise TenantMismatchError("TenantPublicProfile")
        row = await self._session.get(TenantPublicProfileRow, tenant_id.value)
        replacement = public_profile_to_row(entity)
        if row is None:
            self._session.add(replacement)
        else:
            for attribute in (
                "schedule_id",
                "descriptions",
                "public_phone",
                "public_email",
                "website_url",
                "addresses",
                "service_areas",
                "parking_guidance",
                "payment_methods",
                "warranty_policy",
                "appointment_policy",
            ):
                setattr(row, attribute, getattr(replacement, attribute))
        await _flush(self._session, "TenantPublicProfile")


class LeadRepository(SQLAlchemyRepository[Lead, LeadId, LeadRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, LeadRow, lead_to_row, lead_from_row, "Lead")


class HandoffRepository(SQLAlchemyRepository[HandoffCase, HandoffId, HandoffCaseRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, HandoffCaseRow, handoff_to_row, handoff_from_row, "Handoff")


class KnowledgeRepository(
    SQLAlchemyRepository[KnowledgeDocument, DocumentId, KnowledgeDocumentRow]
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(
            session,
            KnowledgeDocumentRow,
            knowledge_to_row,
            knowledge_from_row,
            "KnowledgeDocument",
        )


class BookingRepository(SQLAlchemyRepository[Booking, BookingId, BookingRow]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BookingRow, booking_to_row, booking_from_row, "Booking")

    async def add(self, tenant_id: TenantId, entity: Booking) -> None:
        await super().add(tenant_id, entity)
        for sequence, (from_status, to_status, reason) in enumerate(entity.history, start=1):
            self._session.add(
                BookingStatusHistoryRow(
                    id=uuid4(),
                    tenant_id=tenant_id.value,
                    booking_id=entity.id.value,
                    sequence=sequence,
                    from_status=from_status.value,
                    to_status=to_status.value,
                    reason=reason,
                )
            )
        await _flush(self._session, "Booking")


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, entity_id: ScheduleId) -> BusinessSchedule | None:
        row = await self._session.scalar(
            select(BusinessScheduleRow).where(
                BusinessScheduleRow.tenant_id == tenant_id.value,
                BusinessScheduleRow.id == entity_id.value,
            )
        )
        if row is None:
            return None
        intervals = list(
            (
                await self._session.scalars(
                    select(ScheduleIntervalRow)
                    .where(
                        ScheduleIntervalRow.tenant_id == tenant_id.value,
                        ScheduleIntervalRow.schedule_id == entity_id.value,
                    )
                    .order_by(ScheduleIntervalRow.weekday, ScheduleIntervalRow.start_local)
                )
            ).all()
        )
        overrides = list(
            (
                await self._session.scalars(
                    select(ScheduleOverrideRow)
                    .where(
                        ScheduleOverrideRow.tenant_id == tenant_id.value,
                        ScheduleOverrideRow.schedule_id == entity_id.value,
                    )
                    .order_by(ScheduleOverrideRow.starts_on)
                )
            ).all()
        )
        return schedule_from_rows(row, intervals, overrides)

    async def add(self, tenant_id: TenantId, entity: BusinessSchedule) -> None:
        if entity.tenant_id != tenant_id:
            raise TenantMismatchError("BusinessSchedule")
        row, intervals, overrides = schedule_to_rows(entity)
        self._session.add_all([row, *intervals, *overrides])
        await _flush(self._session, "BusinessSchedule")

    async def list_page(
        self, tenant_id: TenantId, *, cursor: str | None, limit: int
    ) -> Sequence[BusinessSchedule]:
        statement = select(BusinessScheduleRow.id).where(
            BusinessScheduleRow.tenant_id == tenant_id.value
        )
        parsed_cursor = _cursor(cursor)
        if parsed_cursor is not None:
            statement = statement.where(BusinessScheduleRow.id > parsed_cursor)
        ids = list(
            (
                await self._session.scalars(
                    statement.order_by(BusinessScheduleRow.id).limit(_page_limit(limit))
                )
            ).all()
        )
        results: list[BusinessSchedule] = []
        for schedule_id in ids:
            entity = await self.get(tenant_id, ScheduleId(schedule_id))
            if entity is not None:
                results.append(entity)
        return results

    async def replace(self, tenant_id: TenantId, entity: BusinessSchedule) -> None:
        existing = await self.get(tenant_id, entity.id)
        if existing is None:
            await self.add(tenant_id, entity)
            return
        await self._session.execute(
            delete(ScheduleIntervalRow).where(
                ScheduleIntervalRow.tenant_id == tenant_id.value,
                ScheduleIntervalRow.schedule_id == entity.id.value,
            )
        )
        await self._session.execute(
            delete(ScheduleOverrideRow).where(
                ScheduleOverrideRow.tenant_id == tenant_id.value,
                ScheduleOverrideRow.schedule_id == entity.id.value,
            )
        )
        row = await self._session.get(BusinessScheduleRow, entity.id.value)
        if row is not None:
            row.name, row.timezone, row.active = entity.name, entity.timezone, entity.active
        _, intervals, overrides = schedule_to_rows(entity)
        self._session.add_all([*intervals, *overrides])
        await _flush(self._session, "BusinessSchedule")
