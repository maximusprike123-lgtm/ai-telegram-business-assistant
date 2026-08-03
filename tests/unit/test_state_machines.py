from datetime import datetime, timedelta

import pytest

from business_assistant.domain.bookings import Booking, BookingStatus
from business_assistant.domain.conversations import Conversation, ConversationStatus
from business_assistant.domain.handoffs import HandoffCase, HandoffPriority, HandoffStatus
from business_assistant.domain.knowledge import KnowledgeDocument, KnowledgeStatus
from business_assistant.domain.leads import Lead, LeadPriority, LeadStatus
from business_assistant.domain.shared import (
    BookingId,
    ConversationId,
    CustomerId,
    DocumentId,
    HandoffId,
    IdempotencyKey,
    InvalidStateTransition,
    LeadId,
    Locale,
    ServiceId,
    TenantId,
    TenantMismatchError,
    TimeRange,
    ValidationError,
)


def make_booking(
    tenant_id: TenantId,
    customer_id: CustomerId,
    service_id: ServiceId,
    booking_id: BookingId,
    now: datetime,
) -> Booking:
    return Booking(
        booking_id,
        tenant_id,
        customer_id,
        service_id,
        TimeRange(now, now + timedelta(hours=1)),
        IdempotencyKey("booking", "key-1"),
        {"service": "Brake inspection"},
        {"customer_ref": "C-1"},
    )


def test_conversation_handoff_pause_and_resume(
    tenant_id: TenantId,
    customer_id: CustomerId,
    conversation_id: ConversationId,
    now: datetime,
) -> None:
    conversation = Conversation(conversation_id, tenant_id, customer_id, Locale.EN)
    conversation.active_workflow = "booking"
    conversation.touch(now)
    assert conversation.generative_replies_allowed
    conversation.transition_to(ConversationStatus.HANDOFF_QUEUED)
    assert not conversation.generative_replies_allowed
    assert conversation.active_workflow is None
    conversation.transition_to(ConversationStatus.HUMAN_ACTIVE)
    conversation.transition_to(ConversationStatus.ACTIVE_BOT)
    assert conversation.generative_replies_allowed


def test_conversation_rejects_invalid_transition(
    tenant_id: TenantId, customer_id: CustomerId, conversation_id: ConversationId
) -> None:
    conversation = Conversation(conversation_id, tenant_id, customer_id, Locale.EN)
    with pytest.raises(InvalidStateTransition):
        conversation.transition_to(ConversationStatus.HUMAN_ACTIVE)


def test_booking_happy_path_and_history(
    tenant_id: TenantId,
    customer_id: CustomerId,
    service_id: ServiceId,
    booking_id: BookingId,
    now: datetime,
) -> None:
    booking = make_booking(tenant_id, customer_id, service_id, booking_id, now)
    booking.transition_to(BookingStatus.HELD)
    booking.transition_to(BookingStatus.CONFIRMED)
    booking.transition_to(BookingStatus.COMPLETED, reason="service delivered")
    assert booking.status is BookingStatus.COMPLETED
    assert len(booking.history) == 3
    assert booking.history[-1][2] == "service delivered"


def test_booking_expiry_and_terminal_state(
    tenant_id: TenantId,
    customer_id: CustomerId,
    service_id: ServiceId,
    booking_id: BookingId,
    now: datetime,
) -> None:
    booking = make_booking(tenant_id, customer_id, service_id, booking_id, now)
    booking.transition_to(BookingStatus.HELD)
    booking.transition_to(BookingStatus.EXPIRED)
    with pytest.raises(InvalidStateTransition):
        booking.transition_to(BookingStatus.CONFIRMED)


def test_booking_reschedule_can_return_to_confirmed(
    tenant_id: TenantId,
    customer_id: CustomerId,
    service_id: ServiceId,
    booking_id: BookingId,
    now: datetime,
) -> None:
    booking = make_booking(tenant_id, customer_id, service_id, booking_id, now)
    booking.transition_to(BookingStatus.HELD)
    booking.transition_to(BookingStatus.CONFIRMED)
    booking.transition_to(BookingStatus.RESCHEDULE_PENDING)
    booking.transition_to(BookingStatus.CONFIRMED)
    assert booking.status is BookingStatus.CONFIRMED


def test_booking_requires_snapshots_and_rejects_cross_tenant(
    tenant_id: TenantId,
    customer_id: CustomerId,
    service_id: ServiceId,
    booking_id: BookingId,
    now: datetime,
) -> None:
    booking = make_booking(tenant_id, customer_id, service_id, booking_id, now)
    with pytest.raises(TenantMismatchError):
        booking.assert_same_tenant(TenantId.new(), "booking.customer")
    with pytest.raises(ValidationError):
        Booking(
            booking_id,
            tenant_id,
            customer_id,
            service_id,
            TimeRange(now, now + timedelta(hours=1)),
            IdempotencyKey("booking", "key"),
            {},
            {"customer": "x"},
        )


def test_lead_requires_deterministic_score_and_consent(
    tenant_id: TenantId,
    customer_id: CustomerId,
    conversation_id: ConversationId,
    lead_id: LeadId,
    now: datetime,
) -> None:
    lead = Lead(lead_id, tenant_id, customer_id, conversation_id, "vehicle-service", 1, "telegram")
    lead.transition_to(LeadStatus.QUALIFYING)
    lead.record_answer("vehicle", "Kia Rio 2020")
    with pytest.raises(ValidationError):
        lead.qualify()
    lead.apply_deterministic_score(90, LeadPriority.HIGH, {"urgent": 30, "complete": 60})
    lead.grant_consent(now)
    lead.qualify()
    assert lead.status is LeadStatus.QUALIFIED


def test_lead_rejects_answer_after_qualification(
    tenant_id: TenantId,
    customer_id: CustomerId,
    conversation_id: ConversationId,
    lead_id: LeadId,
    now: datetime,
) -> None:
    lead = Lead(lead_id, tenant_id, customer_id, conversation_id, "vehicle", 1, "telegram")
    lead.transition_to(LeadStatus.QUALIFYING)
    lead.apply_deterministic_score(50, LeadPriority.NORMAL, {"base": 50})
    lead.grant_consent(now)
    lead.qualify()
    with pytest.raises(ValidationError):
        lead.record_answer("late", True)
    with pytest.raises(InvalidStateTransition):
        lead.transition_to(LeadStatus.NEW)


def test_handoff_requires_assignee_and_supports_reopen(
    tenant_id: TenantId,
    conversation_id: ConversationId,
    handoff_id: HandoffId,
    now: datetime,
) -> None:
    case = HandoffCase(
        handoff_id,
        tenant_id,
        conversation_id,
        "explicit_request",
        HandoffPriority.NORMAL,
        "Customer requested a person",
        now + timedelta(hours=1),
    )
    with pytest.raises(ValidationError):
        case.transition_to(HandoffStatus.CLAIMED)
    case.transition_to(HandoffStatus.CLAIMED, assignee_id="staff-1")
    case.transition_to(HandoffStatus.RESOLVED)
    case.transition_to(HandoffStatus.REOPENED)
    case.transition_to(HandoffStatus.QUEUED)
    assert case.assignee_id is None


def test_handoff_rejects_invalid_transition(
    tenant_id: TenantId,
    conversation_id: ConversationId,
    handoff_id: HandoffId,
    now: datetime,
) -> None:
    case = HandoffCase(
        handoff_id,
        tenant_id,
        conversation_id,
        "low_confidence",
        HandoffPriority.LOW,
        "No evidence",
        now,
    )
    with pytest.raises(InvalidStateTransition):
        case.transition_to(HandoffStatus.RESOLVED)


def test_knowledge_requires_ready_before_publication(
    tenant_id: TenantId, document_id: DocumentId, now: datetime
) -> None:
    document = KnowledgeDocument(
        document_id, tenant_id, "Warranty", Locale.EN, "markdown", "a" * 64
    )
    with pytest.raises(ValidationError):
        document.publish(now)
    for state in (
        KnowledgeStatus.PARSING,
        KnowledgeStatus.CHUNKING,
        KnowledgeStatus.EMBEDDING,
        KnowledgeStatus.READY,
    ):
        document.transition_to(state)
    document.publish(now)
    assert document.is_searchable
    document.transition_to(KnowledgeStatus.ARCHIVED)
    assert not document.is_searchable


def test_knowledge_failure_can_retry_parsing(tenant_id: TenantId, document_id: DocumentId) -> None:
    document = KnowledgeDocument(document_id, tenant_id, "Policy", Locale.EN, "pdf", "b" * 64)
    document.transition_to(KnowledgeStatus.FAILED)
    document.transition_to(KnowledgeStatus.PARSING)
    with pytest.raises(InvalidStateTransition):
        document.transition_to(KnowledgeStatus.READY)
