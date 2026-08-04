"""Application data contracts for human handoff."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from business_assistant.domain.shared import ConversationId, CustomerId, HandoffId, LeadId, TenantId


@dataclass(frozen=True, slots=True)
class HandoffView:
    id: HandoffId
    tenant_id: TenantId
    customer_id: CustomerId | None
    conversation_id: ConversationId
    lead_id: LeadId | None
    reason_code: str
    priority: str
    status: str
    summary: str
    context: dict[str, Any]
    response_due_at: datetime
    assignee_id: str | None
