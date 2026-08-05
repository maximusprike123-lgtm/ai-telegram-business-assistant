"""Framework-neutral contracts for knowledge ingestion, retrieval, and answers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any
from uuid import UUID

from business_assistant.domain.shared import Citation, DocumentId, Locale, TenantId


class KnowledgeSourceType(StrEnum):
    MARKDOWN = "markdown"
    FAQ = "faq"


@dataclass(frozen=True, slots=True)
class KnowledgeChunkDraft:
    ordinal: int
    text: str
    token_count: int
    checksum: str
    section: str | None = None
    instruction_risk: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ordinal < 0 or not self.text.strip() or self.token_count < 1:
            raise ValueError("Knowledge chunk is invalid")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class PreparedKnowledgeChunk:
    id: UUID
    draft: KnowledgeChunkDraft
    embedding: tuple[float, ...]
    embedding_model: str


@dataclass(frozen=True, slots=True)
class PreparedKnowledgeDocument:
    id: DocumentId
    tenant_id: TenantId
    title: str
    locale: Locale
    source_type: KnowledgeSourceType
    source_text: str
    checksum: str
    chunks: tuple[PreparedKnowledgeChunk, ...]


@dataclass(frozen=True, slots=True)
class KnowledgeReindexCandidate:
    id: UUID
    tenant_id: TenantId
    text: str
    checksum: str


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentView:
    id: DocumentId
    title: str
    locale: Locale
    source_type: KnowledgeSourceType
    checksum: str
    version: int
    status: str
    published_at: datetime | None
    chunk_count: int


@dataclass(frozen=True, slots=True)
class RetrievedKnowledgeChunk:
    document_id: DocumentId
    document_version: int
    chunk_id: UUID
    title: str
    locale: Locale
    source_type: KnowledgeSourceType
    text: str
    section: str | None
    checksum: str
    score: float
    lexical_rank: int | None
    vector_rank: int | None


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    chunk: RetrievedKnowledgeChunk
    citation: Citation


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    answered: bool
    text: str
    evidence: tuple[KnowledgeEvidence, ...]
    fallback_reason: str | None = None
