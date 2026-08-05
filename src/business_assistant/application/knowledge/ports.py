"""Inward-facing embedding and tenant-scoped knowledge persistence ports."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from business_assistant.domain.shared import DocumentId, Locale, TenantId

from .models import (
    KnowledgeDocumentView,
    KnowledgeReindexCandidate,
    PreparedKnowledgeDocument,
    RetrievedKnowledgeChunk,
)


class EmbeddingPort(Protocol):
    provider_name: str

    async def embed(
        self, texts: Sequence[str], *, model: str, dimensions: int
    ) -> tuple[tuple[float, ...], ...]: ...


class KnowledgeStorePort(Protocol):
    async def list_reindex_candidates(
        self, *, embedding_model: str, embedding_dimensions: int, limit: int
    ) -> tuple[KnowledgeReindexCandidate, ...]: ...

    async def update_embedding(
        self,
        candidate: KnowledgeReindexCandidate,
        embedding: Sequence[float],
        *,
        embedding_model: str,
    ) -> bool: ...

    async def find_by_checksum(
        self, tenant_id: TenantId, checksum: str
    ) -> KnowledgeDocumentView | None: ...

    async def ingest(self, document: PreparedKnowledgeDocument) -> KnowledgeDocumentView: ...

    async def publish(
        self, tenant_id: TenantId, document_id: DocumentId, at: datetime
    ) -> KnowledgeDocumentView: ...

    async def archive(
        self, tenant_id: TenantId, document_id: DocumentId
    ) -> KnowledgeDocumentView: ...

    async def hybrid_search(
        self,
        tenant_id: TenantId,
        query: str,
        query_embedding: Sequence[float],
        *,
        locale: Locale,
        embedding_model: str,
        candidate_limit: int,
        result_limit: int,
        at: datetime,
    ) -> tuple[RetrievedKnowledgeChunk, ...]: ...
