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
| FR-005 | 4, 6 | Phase 1 consent invariant and Phase 4 privacy notice implemented; acceptance workflow deferred |
| FR-006 | 4 | Implemented for English-only scope: start/help/catalog/hours/cancel; no language command |
| FR-007 | 2, 4 | Implemented: durable tenant/bot/update processing lifecycle and duplicate/concurrency tests |
| FR-010 | 4 | Implemented: deterministic command, menu, callback, and unknown-text routing |
| FR-011 | 3, 4 | Implemented: validated profile/catalog lookup exposed through Telegram navigation |
| FR-012 | 8 | Planned: published tenant-scoped retrieval |
| FR-013 | 7, 8 | Planned: evidence threshold and safe refusal |
| FR-014 | 2, 8 | Citation value object and versioned knowledge lineage schema implemented; answer use planned |
| FR-015 | 6, 7 | Planned: deterministic risk boundary and handoff |
| FR-020 | 3, 4 | Implemented: active catalog category/service navigation with bounded signed pagination |
| FR-021 | 3 | Implemented: localized service detail, duration, and public price query |
| FR-022 | 1, 3 | Implemented: price presentation invariants and tests |
| FR-023 | 1, 2, 3 | Implemented: public queries enforce active service and category state |
| FR-030 | 6 | Planned: versioned qualification schemas |
| FR-031 | 6, 7 | Planned: extraction, validation, summary, missing fields |
| FR-032 | 6 | Planned: correction workflow |
| FR-033 | 1, 6 | Deterministic score boundary implemented; configured rules planned |
| FR-034 | 1, 2, 6 | Lead fields/consent invariant and persistence mapping implemented; use cases planned |
| FR-035 | 6, 10 | Planned: urgent rules and notifications |
| FR-040 | 3, 5 | Implemented: bookable dates/times rendered in tenant-local time with timezone |
| FR-041 | 3, 5 | Implemented for indivisible capacity units: hours/breaks/overrides, duration/buffer, resources, blackout, bookings/holds, notice/horizon |
| FR-042 | 5 | Implemented: displayed slots require a durable short-lived hold before review |
| FR-043 | 2, 5 | Implemented: locked atomic confirmation, unique idempotency/hold/reference, GiST conflict guard |
| FR-044 | 5, 6 | Implemented for booking: tenant policy bounds required name/phone and optional note |
| FR-045 | 5 | Implemented: safe summary and signed explicit confirmation callback |
| FR-046 | 5 | Implemented: identity-owned idempotent cancellation and atomic new-hold rescheduling under cutoff |
| FR-047 | 1, 2, 5 | Implemented: no hard delete, deterministic lifecycle, ordered status history |
| FR-048 | 5, 10 | Planned: post-commit outbox notifications |
| FR-049 | 5, 10 | Implemented at read/confirm plus bounded manual cleanup; automatic worker deferred by Phase 5 scope |
| FR-050 | 3 | Implemented: override precedence, current status, bounded next-open calculation |
| FR-051 | 3, 4 | Implemented: Telegram renders status, hours, and deterministic next opening |
| FR-052 | 3, 6 | Handoff due-time field implemented; next-open policy planned |
| FR-060 | 4, 9 | Phase 4 stateless navigation/cancel baseline; durable workflow memory remains Phase 9 |
| FR-061 | 9 | Planned: facts with provenance/confidence/sensitivity |
| FR-062 | 9 | Planned: confirmation-state enforcement |
| FR-063 | 9 | Planned: summary authority boundary |
| FR-064 | 4, 5, 9 | Implemented for booking: `/cancel` releases active draft/hold without cancelling appointments |
| FR-065 | 9, 11 | Planned: retention and anonymization workflow |
| FR-070 | 4, 6 | Phase 4 explicit non-creating human-help placeholder; real handoff entry is Phase 6 |
| FR-071 | 6, 7 | Handoff reason model implemented; trigger policy planned |
| FR-072 | 2, 6 | Core handoff model and tenant-scoped persistence implemented; use cases planned |
| FR-073 | 6, 10 | Planned: idempotent admin notification |
| FR-074 | 1, 6 | Implemented: conversation generative-reply pause policy |
| FR-075 | 6 | Lifecycle model implemented; authorization/use cases planned |
| FR-076 | 2, 6, 10 | Durable audit schema implemented; takeover emission planned |
| FR-080 | 10 | Planned: notification subscriptions |
| FR-081 | 10, 11 | PII-minimization ADR accepted; payload implementation planned |
| FR-082 | 3, 6, 8, 10 | Phase 3 protected read-only profile/catalog/schedule API; admin APIs planned |
| FR-083 | 3, 6, 8, 11 | Phase 3 tenant-bound auth/RBAC/input validation; audit/full IdP planned |
| FR-084 | 1, 2, 8 | Knowledge lifecycle/status persistence and chunk schema implemented; ingestion planned |
| FR-090 | 10 | Domain event envelope implemented; analytics catalog/projection planned |
| FR-091 | 10, 11 | Tenant event context implemented; safe dimensions planned |
| FR-092 | 10, 11 | Planned: protected aggregate endpoints |

## Non-functional and baseline ownership

| Specification area | Current baseline | Next enforcement phase |
|---|---|---:|
| Clean Architecture (6.4, 7.2) | Architecture import tests and ADR 0002 | Every phase |
| Tenant isolation (3.3) | Tenant-filtered repositories, composite FKs, integration tests | Every phase |
| UTC/IANA time (6.4, 8.2) | Phase 3 tenant-local schedule engine, DST policy, aware API inputs | 5 slots |
| PostgreSQL/pgvector (7.3, 9) | Async adapter, initial migration, extensions, vector/full-text columns | 8 retrieval |
| Transactional outbox (7.3) | Tenant-scoped durable schema in same database | 10 delivery |
| Privacy/logging (15, 17) | ADR 0004, environment policy, secret scan | 9, 11 |
| CI quality baseline (21, 22) | Ruff, mypy, API/unit/PostgreSQL tests, coverage, build, secret scan | Expanded each phase |
| Docker/runtime (19) | Explicitly deferred | 12 |
| Telegram delivery/idempotency (10, 16, 18) | Authenticated webhook, development polling, durable lifecycle, safe callbacks/logs | 10 outbound outbox, 11 hardening |
