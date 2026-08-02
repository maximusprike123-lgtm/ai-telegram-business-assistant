from datetime import UTC, datetime

import pytest

from business_assistant.domain.shared import (
    BookingId,
    ConversationId,
    CustomerId,
    DocumentId,
    HandoffId,
    LeadId,
    ServiceId,
    TenantId,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def tenant_id() -> TenantId:
    return TenantId.new()


@pytest.fixture
def customer_id() -> CustomerId:
    return CustomerId.new()


@pytest.fixture
def conversation_id() -> ConversationId:
    return ConversationId.new()


@pytest.fixture
def service_id() -> ServiceId:
    return ServiceId.new()


@pytest.fixture
def booking_id() -> BookingId:
    return BookingId.new()


@pytest.fixture
def lead_id() -> LeadId:
    return LeadId.new()


@pytest.fixture
def handoff_id() -> HandoffId:
    return HandoffId.new()


@pytest.fixture
def document_id() -> DocumentId:
    return DocumentId.new()
