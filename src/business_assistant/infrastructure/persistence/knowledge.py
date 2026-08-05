"""Tenant-filtered PostgreSQL ingestion and hybrid knowledge retrieval adapter."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.common.errors import KnowledgeError
from business_assistant.application.knowledge import (
    KnowledgeDocumentView,
    KnowledgeReindexCandidate,
    KnowledgeSourceType,
    PreparedKnowledgeDocument,
    RetrievedKnowledgeChunk,
)
from business_assistant.domain.shared import DocumentId, Locale, TenantId

from .sqlalchemy.models import KnowledgeChunkRow, KnowledgeDocumentRow

_LEXICAL_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "can",
        "do",
        "does",
        "for",
        "how",
        "i",
        "is",
        "it",
        "of",
        "the",
        "to",
        "what",
        "when",
        "where",
        "you",
    }
)


class SQLAlchemyKnowledgeStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def list_reindex_candidates(
        self, *, embedding_model: str, embedding_dimensions: int, limit: int
    ) -> tuple[KnowledgeReindexCandidate, ...]:
        async with self._session_factory() as session:
            rows = (
                await session.scalars(
                    select(KnowledgeChunkRow)
                    .join(
                        KnowledgeDocumentRow,
                        (KnowledgeDocumentRow.tenant_id == KnowledgeChunkRow.tenant_id)
                        & (KnowledgeDocumentRow.id == KnowledgeChunkRow.document_id)
                        & (KnowledgeDocumentRow.version == KnowledgeChunkRow.document_version),
                    )
                    .where(
                        KnowledgeDocumentRow.status == "ready",
                        KnowledgeChunkRow.instruction_risk.is_(False),
                        or_(
                            KnowledgeChunkRow.embedding.is_(None),
                            KnowledgeChunkRow.embedding_model != embedding_model,
                            KnowledgeChunkRow.embedding_dimensions != embedding_dimensions,
                        ),
                    )
                    .order_by(KnowledgeChunkRow.tenant_id, KnowledgeChunkRow.id)
                    .limit(limit)
                )
            ).all()
        return tuple(
            KnowledgeReindexCandidate(row.id, TenantId(row.tenant_id), row.chunk_text, row.checksum)
            for row in rows
        )

    async def update_embedding(
        self,
        candidate: KnowledgeReindexCandidate,
        embedding: Sequence[float],
        *,
        embedding_model: str,
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(KnowledgeChunkRow)
                .where(
                    KnowledgeChunkRow.tenant_id == candidate.tenant_id.value,
                    KnowledgeChunkRow.id == candidate.id,
                    KnowledgeChunkRow.checksum == candidate.checksum,
                )
                .values(
                    embedding=list(embedding),
                    embedding_model=embedding_model,
                    embedding_dimensions=len(embedding),
                )
            )
            return bool(cast(CursorResult[Any], result).rowcount)

    async def find_by_checksum(
        self, tenant_id: TenantId, checksum: str
    ) -> KnowledgeDocumentView | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(KnowledgeDocumentRow).where(
                    KnowledgeDocumentRow.tenant_id == tenant_id.value,
                    KnowledgeDocumentRow.checksum == checksum,
                )
            )
            return await _view(session, row) if row is not None else None

    async def ingest(self, document: PreparedKnowledgeDocument) -> KnowledgeDocumentView:
        async with self._session_factory() as session, session.begin():
            row = KnowledgeDocumentRow(
                id=document.id.value,
                tenant_id=document.tenant_id.value,
                title=document.title,
                locale=document.locale.value,
                source_type=document.source_type.value,
                checksum=document.checksum,
                source_text=document.source_text,
                version=1,
                status="ready",
                published_at=None,
                metadata_json={},
            )
            session.add(row)
            await session.flush()
            session.add_all(
                KnowledgeChunkRow(
                    id=chunk.id,
                    tenant_id=document.tenant_id.value,
                    document_id=document.id.value,
                    document_version=1,
                    ordinal=chunk.draft.ordinal,
                    chunk_text=chunk.draft.text,
                    token_count=chunk.draft.token_count,
                    embedding=list(chunk.embedding),
                    embedding_model=chunk.embedding_model,
                    embedding_dimensions=len(chunk.embedding),
                    instruction_risk=chunk.draft.instruction_risk,
                    metadata_json={
                        **dict(chunk.draft.metadata),
                        "section": chunk.draft.section,
                    },
                    checksum=chunk.draft.checksum,
                )
                for chunk in document.chunks
            )
            await session.flush()
            return await _view(session, row)

    async def publish(
        self, tenant_id: TenantId, document_id: DocumentId, at: datetime
    ) -> KnowledgeDocumentView:
        async with self._session_factory() as session, session.begin():
            row = await _locked_document(session, tenant_id, document_id)
            if row.status != "ready":
                raise KnowledgeError("Only ready knowledge can be published")
            row.published_at = at
            await session.flush()
            return await _view(session, row)

    async def archive(self, tenant_id: TenantId, document_id: DocumentId) -> KnowledgeDocumentView:
        async with self._session_factory() as session, session.begin():
            row = await _locked_document(session, tenant_id, document_id)
            if row.status != "ready":
                raise KnowledgeError("Only ready knowledge can be archived")
            row.status = "archived"
            row.published_at = None
            await session.flush()
            return await _view(session, row)

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
    ) -> tuple[RetrievedKnowledgeChunk, ...]:
        filters = (
            KnowledgeDocumentRow.tenant_id == tenant_id.value,
            KnowledgeChunkRow.tenant_id == tenant_id.value,
            KnowledgeDocumentRow.locale == locale.value,
            KnowledgeDocumentRow.status == "ready",
            KnowledgeDocumentRow.published_at.is_not(None),
            KnowledgeDocumentRow.published_at <= at,
            or_(
                KnowledgeDocumentRow.effective_from.is_(None),
                KnowledgeDocumentRow.effective_from <= at,
            ),
            or_(
                KnowledgeDocumentRow.effective_until.is_(None),
                KnowledgeDocumentRow.effective_until > at,
            ),
            KnowledgeChunkRow.instruction_risk.is_(False),
        )
        join_condition = (
            (KnowledgeDocumentRow.tenant_id == KnowledgeChunkRow.tenant_id)
            & (KnowledgeDocumentRow.id == KnowledgeChunkRow.document_id)
            & (KnowledgeDocumentRow.version == KnowledgeChunkRow.document_version)
        )
        lexical_score = func.ts_rank_cd(
            KnowledgeChunkRow.search_vector,
            func.to_tsquery("simple", _lexical_query(query)),
        )
        distance = KnowledgeChunkRow.embedding.cosine_distance(list(query_embedding))
        async with self._session_factory() as session:
            lexical = (
                await session.execute(
                    select(KnowledgeChunkRow, KnowledgeDocumentRow, lexical_score.label("score"))
                    .join(KnowledgeDocumentRow, join_condition)
                    .where(*filters, lexical_score > 0)
                    .order_by(lexical_score.desc(), KnowledgeChunkRow.id)
                    .limit(candidate_limit)
                )
            ).all()
            vector = (
                await session.execute(
                    select(KnowledgeChunkRow, KnowledgeDocumentRow, distance.label("distance"))
                    .join(KnowledgeDocumentRow, join_condition)
                    .where(
                        *filters,
                        KnowledgeChunkRow.embedding.is_not(None),
                        KnowledgeChunkRow.embedding_model == embedding_model,
                        KnowledgeChunkRow.embedding_dimensions == len(query_embedding),
                    )
                    .order_by(distance, KnowledgeChunkRow.id)
                    .limit(candidate_limit)
                )
            ).all()
        return _fuse(lexical, vector, result_limit, query)


async def _locked_document(
    session: AsyncSession, tenant_id: TenantId, document_id: DocumentId
) -> KnowledgeDocumentRow:
    row = await session.scalar(
        select(KnowledgeDocumentRow)
        .where(
            KnowledgeDocumentRow.tenant_id == tenant_id.value,
            KnowledgeDocumentRow.id == document_id.value,
        )
        .with_for_update()
    )
    if row is None:
        raise KnowledgeError("Knowledge document was not found")
    return row


async def _view(session: AsyncSession, row: KnowledgeDocumentRow) -> KnowledgeDocumentView:
    count = await session.scalar(
        select(func.count())
        .select_from(KnowledgeChunkRow)
        .where(
            KnowledgeChunkRow.tenant_id == row.tenant_id,
            KnowledgeChunkRow.document_id == row.id,
            KnowledgeChunkRow.document_version == row.version,
        )
    )
    return KnowledgeDocumentView(
        DocumentId(row.id),
        row.title,
        Locale(row.locale),
        KnowledgeSourceType(row.source_type),
        row.checksum,
        row.version,
        row.status,
        row.published_at,
        int(count or 0),
    )


def _fuse(
    lexical: Sequence[Any], vector: Sequence[Any], result_limit: int, query: str
) -> tuple[RetrievedKnowledgeChunk, ...]:
    rows: dict[Any, tuple[KnowledgeChunkRow, KnowledgeDocumentRow]] = {}
    lexical_ranks: dict[Any, int] = {}
    vector_ranks: dict[Any, int] = {}
    for rank, (chunk, document, _score) in enumerate(lexical, start=1):
        rows[chunk.id] = (chunk, document)
        lexical_ranks[chunk.id] = rank
    for rank, (chunk, document, _distance) in enumerate(vector, start=1):
        rows[chunk.id] = (chunk, document)
        vector_ranks[chunk.id] = rank
    results: list[RetrievedKnowledgeChunk] = []
    for chunk_id, (chunk, document) in rows.items():
        lexical_rank, vector_rank = lexical_ranks.get(chunk_id), vector_ranks.get(chunk_id)
        reciprocal = sum(
            1 / (60 + rank) for rank in (lexical_rank, vector_rank) if rank is not None
        )
        score = min(1.0, reciprocal * 30.5)
        if lexical_rank is not None:
            query_terms = set(_lexical_terms(query))
            chunk_terms = set(_lexical_terms(chunk.chunk_text))
            coverage = len(query_terms & chunk_terms) / len(query_terms) if query_terms else 0
            score = min(1.0, score + 0.2 * coverage)
        if document.source_type == "faq":
            priority = chunk.metadata_json.get("priority", 0)
            if isinstance(priority, int) and not isinstance(priority, bool):
                score = min(1.0, score + min(priority, 100) * 0.0005)
        section = chunk.metadata_json.get("section")
        results.append(
            RetrievedKnowledgeChunk(
                DocumentId(document.id),
                document.version,
                chunk.id,
                document.title,
                Locale(document.locale),
                KnowledgeSourceType(document.source_type),
                chunk.chunk_text,
                section if isinstance(section, str) else None,
                chunk.checksum,
                score,
                lexical_rank,
                vector_rank,
            )
        )
    results.sort(key=lambda item: (-item.score, str(item.chunk_id)))
    deduplicated: list[RetrievedKnowledgeChunk] = []
    checksums: set[str] = set()
    for result in results:
        if result.checksum in checksums:
            continue
        checksums.add(result.checksum)
        deduplicated.append(result)
        if len(deduplicated) == result_limit:
            break
    return tuple(deduplicated)


def _lexical_query(value: str) -> str:
    terms = _lexical_terms(value)[:50]
    return " | ".join(terms) if terms else "unmatchable"


def _lexical_terms(value: str) -> list[str]:
    return [
        term
        for term in re.findall(r"[A-Za-z0-9]+", value.lower())
        if term not in _LEXICAL_STOP_WORDS
    ]
