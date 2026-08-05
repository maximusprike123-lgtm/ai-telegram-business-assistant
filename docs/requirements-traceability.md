# Requirements traceability baseline

Status values: **implemented** means verified in the repository; **planned** means owned by the
listed roadmap phase and not yet claimed as working. This table tracks implementation ownership,
not acceptance by itself.

| Requirement | Roadmap owner | Status / verification anchor |
|---|---:|---|
| FR-001 | 4 | Implemented: private-chat Telegram identity resolution and stable conversation context |
| FR-002 | 2, 4 | Implemented: tenant-scoped minimal channel identity schema and concurrency-safe adapter |
| FR-003 | 4 | Implemented: deterministic `/start` welcome, demo disclosure, and menu |
| FR-004 | — | Not applicable: the portfolio product is English-only; no language selector is planned |
| FR-005 | 4, 6 | Implemented: versioned purpose-specific accepted/declined decisions precede stored lead answers |
| FR-006 | 4 | Implemented for English-only scope: start/help/catalog/hours/cancel; no language command |
| FR-007 | 2, 4 | Implemented: durable tenant/bot/update processing lifecycle and duplicate/concurrency tests |
| FR-010 | 4 | Implemented: deterministic command, menu, callback, and unknown-text routing |
| FR-011 | 3, 4 | Implemented: validated profile/catalog lookup exposed through Telegram navigation |
| FR-012 | 8 | Implemented: tenant/locale/ready/publication/effective-date/injection filters precede lexical and vector ranking |
| FR-013 | 7, 8 | Implemented: model confidence plus retrieval evidence gates and deterministic refusal/handoff fallback |
| FR-014 | 2, 8 | Partially implemented: answer evidence carries document/version/chunk/score/checksum citations and customer-safe labels; durable association with stored outbound messages awaits message persistence |
| FR-015 | 6, 7 | Implemented: structured safety rules plus allowlisted free-text risk classification with deterministic safe fallback |
| FR-020 | 3, 4 | Implemented: active catalog category/service navigation with bounded signed pagination |
| FR-021 | 3 | Implemented: localized service detail, duration, and public price query |
| FR-022 | 1, 3 | Implemented: price presentation invariants and tests |
| FR-023 | 1, 2, 3 | Implemented: public queries enforce active service and category state |
| FR-030 | 6 | Implemented: tenant-owned versioned typed schemas with protected draft/publish operations |
| FR-031 | 6, 7 | Implemented: deterministic validation/review plus schema-allowlisted advisory AI extraction; application rules remain authoritative |
| FR-032 | 6 | Implemented: individual persisted answer edit without workflow restart |
| FR-033 | 1, 6 | Implemented: configured deterministic rules, bounded score, grade, and matched explanation |
| FR-034 | 1, 2, 6 | Implemented: consent, source, schema snapshot, score, timestamps, and lead lifecycle use case |
| FR-035 | 6, 10 | Implemented: urgent rules, atomic outbox intent, tenant subscription projection, and reliable delivery |
| FR-040 | 3, 5 | Implemented: bookable dates/times rendered in tenant-local time with timezone |
| FR-041 | 3, 5 | Implemented for indivisible capacity units: hours/breaks/overrides, duration/buffer, resources, blackout, bookings/holds, notice/horizon |
| FR-042 | 5 | Implemented: displayed slots require a durable short-lived hold before review |
| FR-043 | 2, 5 | Implemented: locked atomic confirmation, unique idempotency/hold/reference, GiST conflict guard |
| FR-044 | 5, 6 | Implemented for booking: tenant policy bounds required name/phone and optional note |
| FR-045 | 5 | Implemented: safe summary and signed explicit confirmation callback |
| FR-046 | 5 | Implemented: identity-owned idempotent cancellation and atomic new-hold rescheduling under cutoff |
| FR-047 | 1, 2, 5 | Implemented: no hard delete, deterministic lifecycle, ordered status history |
| FR-048 | 5, 10 | Implemented: atomic booking lifecycle outbox events and post-commit staff notification delivery |
| FR-049 | 5, 10 | Implemented: read/confirm expiry plus bounded scheduled worker using the Phase 5 transaction |
| FR-050 | 3 | Implemented: override precedence, current status, bounded next-open calculation |
| FR-051 | 3, 4 | Implemented: Telegram renders status, hours, and deterministic next opening |
| FR-052 | 3, 6 | Implemented: response due time consumes effective tenant business intervals |
| FR-060 | 4, future | Phase 4 stateless navigation/cancel baseline; durable workflow memory deferred by approved Phase 9 privacy-only scope |
| FR-061 | future | Planned: facts with provenance/confidence/sensitivity; excluded from privacy-only Phase 9 |
| FR-062 | future | Planned: confirmation-state enforcement; excluded from privacy-only Phase 9 |
| FR-063 | future | Planned: summary authority boundary; excluded from privacy-only Phase 9 |
| FR-064 | 4, 5, 9 | Implemented for booking: `/cancel` releases active draft/hold without cancelling appointments |
| FR-065 | 9, 11 | Implemented: tenant policy, preview, confirmed/idempotent retention execution, customer anonymization, and audit preservation; export/legal-hold/backup controls remain hardening scope |
| FR-070 | 4, 6 | Implemented: explicit Telegram human request creates/reuses a durable case |
| FR-071 | 6, 7 | Explicit, unsupported, structured-safety, AI refusal/low-confidence, and unsafe-output handoff fallbacks implemented; repeated-failure policy remains deferred |
| FR-072 | 2, 6 | Implemented: linked case, priority, safe structured context, summary, status, and due timestamp |
| FR-073 | 6, 10 | Implemented: idempotent outbox intent, tenant-owned staff recipients, retries, and dead letters |
| FR-074 | 1, 6 | Implemented: conversation generative-reply pause policy |
| FR-075 | 6 | Implemented: RBAC-protected claim, resolve, reopen, and return-control use cases/API |
| FR-076 | 2, 6, 10 | Implemented: every staff takeover/control action appends a durable audit event |
| FR-080 | 10 | Implemented for Telegram staff recipients and lead/handoff event subscriptions |
| FR-081 | 10, 11 | Implemented for Phase 10: allowlisted templates and PII-minimized event payloads; broader hardening remains Phase 11 |
| FR-082 | 3, 6, 8, 10 | Qualification plus Markdown/FAQ knowledge ingest/publish/archive/test-answer API implemented; remaining admin resources stay phased |
| FR-083 | 3, 6, 8, 11 | Tenant-derived qualification/handoff/knowledge RBAC and input validation implemented; full IdP remains deferred |
| FR-084 | 1, 2, 8 | Implemented for synchronous Markdown/FAQ: lifecycle, deterministic chunking, embedding, ready/publish/archive status |
| FR-090 | 10 | Domain event envelope implemented; analytics catalog/projection planned |
| FR-091 | 10, 11 | Implemented: tenant event context plus fixed safe operational metric dimensions |
| FR-092 | 10, 11 | Implemented: authenticated diagnostics and protected low-cardinality metrics endpoint |

## Non-functional and baseline ownership

| Specification area | Current baseline | Next enforcement phase |
|---|---|---:|
| Clean Architecture (6.4, 7.2) | Architecture import tests and ADR 0002 | Every phase |
| Tenant isolation (3.3) | Tenant-filtered repositories, composite FKs, integration tests | Every phase |
| UTC/IANA time (6.4, 8.2) | Phase 3 tenant-local schedule engine, DST policy, aware API inputs | 5 slots |
| PostgreSQL/pgvector (7.3, 9) | Tenant-filtered hybrid full-text/cosine retrieval with typed embedding metadata | Index benchmarking |
| Transactional outbox (7.3) | PostgreSQL-authoritative idempotent projection, leases, retries, and dead letters | Continued hardening |
| Privacy/logging (15, 17) | Phase 11 constant-event allowlisted logs, bounded metrics, ADR 0004/0012/0014, secret scan | Continued review |
| AI gateway/safety (7.4, 12, 16) | Provider-neutral generation/embedding ports, strict validation, evidence grounding, metadata-only telemetry | Continued evaluation |
| CI quality baseline (21, 22) | Ruff, mypy, API/unit/PostgreSQL tests, coverage, build, secret scan | Expanded each phase |
| Docker/runtime (19) | Explicitly deferred | 12 |
| Telegram delivery/idempotency (10, 16, 18) | Authenticated webhook, development polling, durable lifecycle, safe callbacks/logs | 10 outbound outbox, 11 hardening |
