"""Tenant-scoped synchronous ingestion and evidence-backed answer use cases."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from business_assistant.application.ai import AIProviderError
from business_assistant.application.common.errors import KnowledgeError
from business_assistant.application.common.security import Permission, Principal
from business_assistant.application.observability import (
    Component,
    Operation,
    OperationalMetricsPort,
    Outcome,
)
from business_assistant.domain.knowledge import KnowledgeDocument, KnowledgeStatus
from business_assistant.domain.shared import Citation, Confidence, DocumentId, Locale, TenantId

from .chunking import DeterministicKnowledgeChunker, content_checksum, normalize_source
from .models import (
    KnowledgeAnswer,
    KnowledgeChunkDraft,
    KnowledgeDocumentView,
    KnowledgeEvidence,
    KnowledgeSourceType,
    PreparedKnowledgeChunk,
    PreparedKnowledgeDocument,
)
from .ports import EmbeddingPort, KnowledgeStorePort


@dataclass(frozen=True, slots=True)
class KnowledgePolicy:
    embedding_model: str
    embedding_dimensions: int
    candidate_limit: int = 20
    result_limit: int = 4
    minimum_relevance: float = 0.6
    maximum_answer_characters: int = 1800
    maximum_source_bytes: int = 10_485_760

    def __post_init__(self) -> None:
        if not self.embedding_model.strip() or not 1 <= self.embedding_dimensions <= 4096:
            raise ValueError("Knowledge embedding policy is invalid")
        if not 1 <= self.result_limit <= self.candidate_limit <= 100:
            raise ValueError("Knowledge retrieval limits are invalid")
        if not 0.5 <= self.minimum_relevance <= 1:
            raise ValueError("Knowledge relevance threshold is invalid")
        if not 200 <= self.maximum_answer_characters <= 4000:
            raise ValueError("Knowledge answer limit is invalid")
        if not 1024 <= self.maximum_source_bytes <= 1_073_741_824:
            raise ValueError("Knowledge source limit is invalid")


class KnowledgeApplication:
    def __init__(
        self,
        store: KnowledgeStorePort,
        embeddings: EmbeddingPort,
        chunker: DeterministicKnowledgeChunker,
        policy: KnowledgePolicy,
        metrics: OperationalMetricsPort | None = None,
    ) -> None:
        self._store = store
        self._embeddings = embeddings
        self._chunker = chunker
        self._policy = policy
        self._metrics = metrics

    async def ingest_markdown(
        self, principal: Principal, *, title: str, markdown: str, locale: str
    ) -> KnowledgeDocumentView:
        principal.require(Permission.KNOWLEDGE_WRITE)
        source = normalize_source(markdown)
        return await self._ingest(
            principal,
            title=title,
            source=source,
            locale=_locale(locale),
            source_type=KnowledgeSourceType.MARKDOWN,
            drafts=self._chunker.markdown(source),
        )

    async def ingest_faq(
        self,
        principal: Principal,
        *,
        question: str,
        answer: str,
        aliases: tuple[str, ...] = (),
        priority: int = 0,
        locale: str,
    ) -> KnowledgeDocumentView:
        principal.require(Permission.KNOWLEDGE_WRITE)
        drafts = self._chunker.faq(question, answer, aliases=aliases, priority=priority)
        source = drafts[0].text
        return await self._ingest(
            principal,
            title=normalize_source(question),
            source=source,
            locale=_locale(locale),
            source_type=KnowledgeSourceType.FAQ,
            drafts=drafts,
        )

    async def publish(
        self, principal: Principal, document_id: DocumentId, *, at: datetime | None = None
    ) -> KnowledgeDocumentView:
        principal.require(Permission.KNOWLEDGE_WRITE)
        published_at = at or datetime.now(UTC)
        if published_at.tzinfo is None or published_at.utcoffset() is None:
            raise KnowledgeError("Knowledge publication time must be timezone-aware")
        return await self._store.publish(principal.tenant_id, document_id, published_at)

    async def archive(self, principal: Principal, document_id: DocumentId) -> KnowledgeDocumentView:
        principal.require(Permission.KNOWLEDGE_WRITE)
        return await self._store.archive(principal.tenant_id, document_id)

    async def answer(
        self, principal: Principal, *, query: str, locale: str = "en"
    ) -> KnowledgeAnswer:
        principal.require(Permission.KNOWLEDGE_READ)
        return await self.answer_for_tenant(
            principal.tenant_id,
            query=query,
            locale=locale,
        )

    async def answer_for_tenant(
        self, tenant_id: TenantId, *, query: str, locale: str = "en"
    ) -> KnowledgeAnswer:
        started = monotonic()
        query_value = normalize_source(query)
        if not query_value or len(query_value) > 2000:
            raise KnowledgeError("Knowledge query must contain 1-2000 characters")
        try:
            vectors = await self._embeddings.embed(
                (query_value,),
                model=self._policy.embedding_model,
                dimensions=self._policy.embedding_dimensions,
            )
            _validate_embeddings(vectors, 1, self._policy.embedding_dimensions)
            candidates = await self._store.hybrid_search(
                tenant_id,
                query_value,
                vectors[0],
                locale=_locale(locale),
                embedding_model=self._policy.embedding_model,
                candidate_limit=self._policy.candidate_limit,
                result_limit=self._policy.result_limit,
                at=datetime.now(UTC),
            )
        except asyncio.CancelledError:
            raise
        except (AIProviderError, KnowledgeError, ValueError):
            self._observe(Outcome.DEGRADED, started)
            return _fallback("retrieval_unavailable")
        eligible = tuple(
            item for item in candidates if item.score >= self._policy.minimum_relevance
        )
        if not eligible:
            self._observe(Outcome.DEGRADED, started)
            return _fallback("insufficient_evidence")
        evidence = tuple(
            KnowledgeEvidence(
                item,
                Citation(
                    item.document_id,
                    item.document_version,
                    str(item.chunk_id),
                    Confidence(min(1.0, max(0.0, item.score))),
                    item.checksum,
                ),
            )
            for item in eligible
        )
        answer = _extractive_answer(evidence, self._policy.maximum_answer_characters)
        self._observe(Outcome.SUCCESS, started)
        return KnowledgeAnswer(True, answer, evidence)

    def _observe(self, outcome: Outcome, started: float) -> None:
        if self._metrics is not None:
            self._metrics.observe(
                Component.RETRIEVAL,
                Operation.SEARCH,
                outcome,
                monotonic() - started,
            )

    async def reindex(self, *, limit: int = 100) -> int:
        if not 1 <= limit <= 1000:
            raise KnowledgeError("Knowledge re-index batch size is invalid")
        candidates = await self._store.list_reindex_candidates(
            embedding_model=self._policy.embedding_model,
            embedding_dimensions=self._policy.embedding_dimensions,
            limit=limit,
        )
        if not candidates:
            return 0
        vectors = await self._embeddings.embed(
            tuple(item.text for item in candidates),
            model=self._policy.embedding_model,
            dimensions=self._policy.embedding_dimensions,
        )
        _validate_embeddings(vectors, len(candidates), self._policy.embedding_dimensions)
        updated = 0
        for candidate, vector in zip(candidates, vectors, strict=True):
            updated += int(
                await self._store.update_embedding(
                    candidate, vector, embedding_model=self._policy.embedding_model
                )
            )
        return updated

    async def _ingest(
        self,
        principal: Principal,
        *,
        title: str,
        source: str,
        locale: Locale,
        source_type: KnowledgeSourceType,
        drafts: tuple[KnowledgeChunkDraft, ...],
    ) -> KnowledgeDocumentView:
        if (
            not title.strip()
            or len(title) > 300
            or len(source.encode("utf-8")) > self._policy.maximum_source_bytes
        ):
            raise KnowledgeError("Knowledge source title or size is invalid")
        checksum = content_checksum(source)
        existing = await self._store.find_by_checksum(principal.tenant_id, checksum)
        if existing is not None:
            return existing
        document_id = DocumentId.new()
        lifecycle = KnowledgeDocument(
            document_id, principal.tenant_id, title, locale, source_type.value, checksum
        )
        lifecycle.transition_to(KnowledgeStatus.PARSING)
        lifecycle.transition_to(KnowledgeStatus.CHUNKING)
        lifecycle.transition_to(KnowledgeStatus.EMBEDDING)
        try:
            vectors = await self._embeddings.embed(
                tuple(draft.text for draft in drafts),
                model=self._policy.embedding_model,
                dimensions=self._policy.embedding_dimensions,
            )
        except asyncio.CancelledError:
            raise
        except AIProviderError as exc:
            raise KnowledgeError("Knowledge embedding is temporarily unavailable") from exc
        _validate_embeddings(vectors, len(drafts), self._policy.embedding_dimensions)
        lifecycle.transition_to(KnowledgeStatus.READY)
        prepared = PreparedKnowledgeDocument(
            document_id,
            principal.tenant_id,
            title.strip(),
            locale,
            source_type,
            source,
            checksum,
            tuple(
                PreparedKnowledgeChunk(uuid4(), draft, vector, self._policy.embedding_model)
                for draft, vector in zip(drafts, vectors, strict=True)
            ),
        )
        return await self._store.ingest(prepared)


def _locale(value: str) -> Locale:
    _ = value
    return Locale.EN


def _validate_embeddings(
    vectors: tuple[tuple[float, ...], ...], expected_count: int, dimensions: int
) -> None:
    if len(vectors) != expected_count or any(len(vector) != dimensions for vector in vectors):
        raise KnowledgeError("Embedding response shape is invalid")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise KnowledgeError("Embedding response contains invalid values")


def _fallback(reason: str) -> KnowledgeAnswer:
    return KnowledgeAnswer(
        False,
        "I don't have enough approved information to answer that reliably. "
        "Please ask a more specific question or contact the team.",
        (),
        reason,
    )


def _extractive_answer(evidence: tuple[KnowledgeEvidence, ...], maximum: int) -> str:
    parts: list[str] = []
    size = 0
    for item in evidence:
        text = item.chunk.text.strip()
        separator = "\n\n" if parts else ""
        available = maximum - size - len(separator)
        if available <= 0:
            break
        value = text if len(text) <= available else text[:available].rsplit(" ", 1)[0].rstrip()
        if value:
            parts.append(value)
            size += len(separator) + len(value)
        if len(text) > available:
            break
    return "\n\n".join(parts)
