"""Privacy classifications, tenant retention policy, and workflow results."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from business_assistant.domain.shared import TenantId


class DataClass(StrEnum):
    OPERATIONAL_METADATA = "operational_metadata"
    MESSAGE_CONTENT = "message_content"
    CUSTOMER_CONTACT = "customer_contact"
    WORKFLOW_RECORDS = "workflow_records"
    KNOWLEDGE = "knowledge"
    AUDIT_SECURITY = "audit_security"
    AI_TELEMETRY = "ai_telemetry"


class RetentionAction(StrEnum):
    DELETE = "delete"
    ANONYMIZE = "anonymize"
    PRESERVE = "preserve"


@dataclass(frozen=True, slots=True)
class DataClassification:
    data_class: DataClass
    purpose: str
    sensitivity: str
    retention_action: RetentionAction


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    tenant_id: TenantId
    version: int
    operational_metadata_days: int
    message_content_days: int
    customer_contact_days: int
    workflow_records_days: int
    knowledge_archive_days: int
    ai_telemetry_days: int
    automatic_execution_enabled: bool = False

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError("Retention policy version must be positive")
        periods = (
            self.operational_metadata_days,
            self.message_content_days,
            self.customer_contact_days,
            self.workflow_records_days,
            self.knowledge_archive_days,
            self.ai_telemetry_days,
        )
        if any(not 1 <= value <= 3650 for value in periods):
            raise ValueError("Retention periods must be between 1 and 3650 days")


@dataclass(frozen=True, slots=True)
class PrivacyResult:
    action_id: str | None
    action: str
    dry_run: bool
    policy_version: int
    counts: Mapping[str, int]
    idempotent_replay: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", MappingProxyType(dict(self.counts)))
        if any(value < 0 for value in self.counts.values()):
            raise ValueError("Privacy result counts cannot be negative")


CLASSIFICATIONS = (
    DataClassification(
        DataClass.OPERATIONAL_METADATA,
        "Delivery deduplication, reliability, and bounded operational diagnosis.",
        "internal",
        RetentionAction.DELETE,
    ),
    DataClassification(
        DataClass.MESSAGE_CONTENT,
        "Customer interaction processing where explicitly persisted.",
        "personal",
        RetentionAction.DELETE,
    ),
    DataClassification(
        DataClass.CUSTOMER_CONTACT,
        "Identity resolution, requested contact, booking, and lead workflows.",
        "personal",
        RetentionAction.ANONYMIZE,
    ),
    DataClassification(
        DataClass.WORKFLOW_RECORDS,
        "Booking, lead, qualification, and handoff history.",
        "mixed",
        RetentionAction.ANONYMIZE,
    ),
    DataClassification(
        DataClass.KNOWLEDGE,
        "Approved tenant business information and retrieval lineage.",
        "business",
        RetentionAction.DELETE,
    ),
    DataClassification(
        DataClass.AUDIT_SECURITY,
        "Accountability for authorized security and business actions.",
        "restricted",
        RetentionAction.PRESERVE,
    ),
    DataClassification(
        DataClass.AI_TELEMETRY,
        "Provider reliability, latency, usage, and safe failure analysis.",
        "internal",
        RetentionAction.DELETE,
    ),
)
