import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from ..shared import (
    DocumentId,
    InvalidStateTransition,
    Locale,
    TenantId,
    ValidationError,
    ensure_aware,
)


class KnowledgeStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"


_TRANSITIONS: dict[KnowledgeStatus, frozenset[KnowledgeStatus]] = {
    KnowledgeStatus.UPLOADED: frozenset({KnowledgeStatus.PARSING, KnowledgeStatus.FAILED}),
    KnowledgeStatus.PARSING: frozenset({KnowledgeStatus.CHUNKING, KnowledgeStatus.FAILED}),
    KnowledgeStatus.CHUNKING: frozenset({KnowledgeStatus.EMBEDDING, KnowledgeStatus.FAILED}),
    KnowledgeStatus.EMBEDDING: frozenset({KnowledgeStatus.READY, KnowledgeStatus.FAILED}),
    KnowledgeStatus.READY: frozenset({KnowledgeStatus.ARCHIVED}),
    KnowledgeStatus.FAILED: frozenset({KnowledgeStatus.PARSING, KnowledgeStatus.ARCHIVED}),
    KnowledgeStatus.ARCHIVED: frozenset(),
}


@dataclass(slots=True)
class KnowledgeDocument:
    id: DocumentId
    tenant_id: TenantId
    title: str
    locale: Locale
    source_type: str
    checksum: str
    version: int = 1
    status: KnowledgeStatus = KnowledgeStatus.UPLOADED
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.source_type.strip():
            raise ValidationError("Knowledge title and source type are required")
        if not re.fullmatch(r"[a-fA-F0-9]{32,128}", self.checksum):
            raise ValidationError("Knowledge checksum must be hexadecimal")
        if self.version < 1:
            raise ValidationError("Knowledge version must be positive")
        if self.published_at is not None:
            ensure_aware(self.published_at, "published_at")
            if self.status is not KnowledgeStatus.READY:
                raise ValidationError("Only ready knowledge can be published")

    @property
    def is_searchable(self) -> bool:
        return self.status is KnowledgeStatus.READY and self.published_at is not None

    def transition_to(self, target: KnowledgeStatus) -> None:
        if target not in _TRANSITIONS[self.status]:
            raise InvalidStateTransition("KnowledgeDocument", self.status, target)
        self.status = target
        if target is KnowledgeStatus.ARCHIVED:
            self.published_at = None

    def publish(self, at: datetime) -> None:
        if self.status is not KnowledgeStatus.READY:
            raise ValidationError("Only ready knowledge can be published")
        self.published_at = ensure_aware(at, "published_at")
