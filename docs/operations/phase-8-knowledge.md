# Phase 8 knowledge and retrieval runbook

## Enable locally

Knowledge remains off by default. Apply migrations and configure the existing AI provider plus an
embedding model that supports the configured output dimensions:

```bash
AI_ENABLED=true
FEATURE_RAG_ENABLED=true
AI_PROVIDER=openai
AI_ROUTER_MODEL=<approved-router-model>
AI_RESPONSE_MODEL=<approved-response-model>
OPENAI_EMBEDDING_MODEL=<approved-embedding-model>
EMBEDDING_DIMENSIONS=<approved-dimensions>
OPENAI_API_KEY=<secret-manager-value>
```

The adapter uses OpenAI's embeddings endpoint. No model name or price is hard-coded. The
credential stays in an ignored `.env` or secret manager.

## Ingest and publish

The protected internal API derives tenant scope from `X-Internal-API-Key`; a request body cannot
select a tenant. Owner, manager, and knowledge-editor roles may write. Viewer may test approved
answers but cannot ingest or publish; agent has the same read-only knowledge permission.

- `POST /api/v1/knowledge/markdown`
- `POST /api/v1/knowledge/faqs`
- `POST /api/v1/knowledge/documents/{id}/publish`
- `POST /api/v1/knowledge/documents/{id}/archive`
- `POST /api/v1/knowledge/test-answer`

Ingestion is synchronous and bounded by `UPLOAD_MAX_BYTES`. A checksum-identical source is
idempotent for the tenant. New content becomes `ready` but remains unsearchable until explicitly
published. Archiving removes it from search without deleting lineage.

FAQ answers remain one chunk. Markdown chunks follow headings, configured maximum tokens, and
overlap. Instruction-like content is retained for review but marked and excluded from retrieval.
Do not publish unreviewed customer content as knowledge.

## Retrieval and fallback

Both lexical and vector branches apply tenant, English locale, publication, ready status,
effective date, and instruction-risk filters before ranking. Results are fused and deduplicated.
`RAG_MIN_RELEVANCE` cannot be configured below `0.5`; the default `0.6` rejects a vector-only weak
match while permitting strong lexical evidence or corroborated hybrid evidence.

Answers are extracts of approved evidence and include document/version/chunk/checksum citations in
the application/API result. Telegram presents safe source labels. If embeddings are unavailable or
evidence is insufficient, the answer is not generated and Telegram uses the existing human-help
fallback.

## Rollback and model changes

Disable `FEATURE_RAG_ENABLED` for immediate deterministic fallback. Disable `AI_ENABLED` to stop
all provider calls. Revision `0007_phase8` is reversible and adds source text plus typed embedding
model/dimension and instruction-risk metadata; it does not delete existing knowledge.

Changing model or dimensions makes old embeddings ineligible by design. Re-ingestion automation is
not part of this phase; archive and ingest an approved replacement manually. Approximate-vector
index selection also remains deferred until representative retrieval benchmarks exist.
