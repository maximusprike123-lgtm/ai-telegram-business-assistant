# Phase 8 completion traceability

| Phase 8 contract | Implementation and verification anchor |
|---|---|
| Tenant-scoped storage | Composite knowledge lineage FKs, tenant predicates in every write/search branch, cross-tenant integration test |
| Markdown ingestion | Normalization, heading-preserving deterministic chunker, source/chunk checksums, bounded API contract |
| FAQ ingestion | Curated question/answer/aliases/priority preserved as one immutable source/chunk |
| Embeddings | Provider-neutral application port, isolated OpenAI adapter, batch/order/dimension/finite-value contract tests |
| pgvector | Existing vector column plus revision 0007 typed model/dimension consistency constraint |
| Hybrid retrieval | PostgreSQL full-text and cosine candidate sets, deterministic fusion, lexical coverage, FAQ boost, checksum deduplication |
| Retrieval filters | Tenant, English locale, ready/published, effective dates, injection flag, model, and dimension applied before ranking |
| Evidence policy | Minimum relevance gate, exact extractive evidence, bounded answer, deterministic refusal |
| Citations | Document/version/chunk/score/checksum lineage in application and API results; Telegram source labels; durable outbound-message association is explicitly deferred |
| Publication workflow | Ready-but-unpublished ingestion, explicit publish, archive, idempotent duplicate checksum |
| Prompt injection | Instruction-like source flagged during ingestion and excluded in both retrieval paths |
| Protected API | Existing tenant-derived authentication plus owner/manager/knowledge-editor write RBAC and OpenAPI tests |
| Customer integration | Phase 7 permits only the read-only FAQ route; no knowledge mutation or tool/action schema |

Explicitly deferred: background ingestion workers/retries, PDF/DOCX/OCR, websites/drives, generated
answer prose, reranker implementation, approximate vector indexes, agents, tools, memory, and admin
dashboard.
