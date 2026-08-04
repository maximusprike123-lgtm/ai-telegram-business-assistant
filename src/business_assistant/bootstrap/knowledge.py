"""Phase 8 knowledge composition using existing provider and PostgreSQL boundaries."""

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from business_assistant.application.knowledge import (
    DeterministicKnowledgeChunker,
    KnowledgeApplication,
    KnowledgePolicy,
)
from business_assistant.config import RuntimeSettings
from business_assistant.infrastructure.ai import OpenAIEmbeddingsAdapter
from business_assistant.infrastructure.persistence import SQLAlchemyKnowledgeStore


def build_knowledge_application(
    settings: RuntimeSettings,
    session_factory: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient | None,
) -> KnowledgeApplication | None:
    if not settings.features.rag_enabled:
        return None
    if (
        client is None
        or settings.openai.api_key is None
        or settings.openai.embedding_model is None
        or settings.openai.embedding_dimensions is None
    ):
        raise ValueError("Enabled knowledge retrieval requires an embedding provider policy")
    return KnowledgeApplication(
        SQLAlchemyKnowledgeStore(session_factory),
        OpenAIEmbeddingsAdapter(
            client,
            settings.openai.api_key,
            base_url=settings.openai.base_url,
        ),
        DeterministicKnowledgeChunker(
            settings.knowledge.chunk_max_tokens,
            settings.knowledge.chunk_overlap_tokens,
        ),
        KnowledgePolicy(
            embedding_model=settings.openai.embedding_model,
            embedding_dimensions=settings.openai.embedding_dimensions,
            candidate_limit=settings.knowledge.candidate_limit,
            result_limit=settings.knowledge.result_limit,
            minimum_relevance=settings.knowledge.minimum_relevance,
            maximum_answer_characters=settings.knowledge.maximum_answer_characters,
            maximum_source_bytes=settings.limits.upload_max_bytes,
        ),
    )
