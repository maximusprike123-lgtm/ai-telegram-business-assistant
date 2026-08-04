# ADR 0011: Phase 8 tenant-scoped knowledge retrieval

- Status: Accepted
- Date: 2026-08-04

## Context

The Phase 2 schema already stores tenant-owned knowledge documents/chunks, generated full-text
vectors, nullable pgvector embeddings, and citation lineage. Phase 8 must make that foundation
usable without allowing retrieved text, embedding providers, or generated prose to bypass tenant,
publication, evidence, or application policy. This phase explicitly excludes workers, PDF/OCR,
website crawling, tools, agents, memory, and external-drive integrations.

## Decision

- Keep parsing, deterministic chunking, evidence thresholds, citation construction, and fallback
  policy in `application.knowledge`. Keep SQLAlchemy, pgvector, and OpenAI HTTP contracts in
  infrastructure adapters behind inward-facing ports.
- Accept bounded English Markdown and curated FAQ input synchronously. Normalize FAQ question and
  answer as one immutable knowledge document/chunk so it shares publication, checksum, embedding,
  retrieval, and citation lineage with Markdown. Do not add a parallel FAQ authority table.
- Preserve normalized source text for audit/reprocessing. Chunk Markdown at heading boundaries,
  never merge sections, use configured token windows/overlap, and checksum every source and chunk.
- Flag instruction-like source content during ingestion and exclude flagged chunks in every
  retrieval branch. Source content remains untrusted even after publication.
- Add a provider-neutral embedding port and an isolated OpenAI `/v1/embeddings` adapter. Model and
  dimensions are deployment configuration; returned batch order, count, dimensions, and finite
  values are validated before persistence.
- Apply tenant, English locale, ready/published status, effective dates, instruction-risk,
  embedding-model, and dimension filters before ranking. Retrieve lexical and cosine candidates
  independently, fuse ranks deterministically, add bounded lexical coverage/FAQ-priority boosts,
  and deduplicate by chunk checksum.
- Require the configured evidence threshold before answering. Customer answers are bounded
  extractive text from approved chunks, not unconstrained model prose. Citations carry document,
  version, chunk, relevance, and checksum lineage; insufficient evidence or provider failure uses
  a deterministic refusal/human-help path.
- Permit the Phase 7 router to select one new read-only `faq_knowledge` route. It cannot mutate
  knowledge or perform a consequential action. Protected ingestion/publication/test-answer API
  operations use the existing tenant-derived principal and application RBAC.
- Keep exact vector scans for the current portfolio dataset. Do not add HNSW/IVFFlat before a
  representative corpus and retrieval benchmark justify dimensions, operator, and index policy.

## Consequences

No provider or document can select another tenant, unpublished content is never ranked, and an
answer always exposes internally verifiable evidence. The synchronous API is intentionally bounded
and suitable for a portfolio dataset, but large-source processing, retry queues, reprocessing,
batch telemetry, approximate vector indexes, and richer version replacement remain later work.
Changing the embedding model or dimensions requires re-ingestion because incompatible vectors are
filtered before search.
