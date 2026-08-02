# Requirements traceability baseline

Status values: **implemented** means verified in the repository; **planned** means owned by the
listed roadmap phase and not yet claimed as working. This table tracks implementation ownership,
not acceptance by itself.

| Requirement | Roadmap owner | Status / verification anchor |
|---|---:|---|
| FR-001 | 4 | Planned: Telegram identity resolution |
| FR-002 | 2, 4 | Planned: channel identity persistence and adapter |
| FR-003 | 4 | Planned: deterministic onboarding disclosure |
| FR-004 | 4 | Planned: RU/EN detection and preference |
| FR-005 | 4, 6 | Phase 1 consent invariant implemented; notice flow planned |
| FR-006 | 4 | Planned: deterministic Telegram commands |
| FR-007 | 2, 4 | Planned: persistence and update/workflow idempotency |
| FR-010 | 4 | Planned: deterministic routing and copy |
| FR-011 | 3, 4 | Planned: canonical configuration/catalog lookup |
| FR-012 | 8 | Planned: published tenant-scoped retrieval |
| FR-013 | 7, 8 | Planned: evidence threshold and safe refusal |
| FR-014 | 2, 8 | Citation value object implemented; message lineage planned |
| FR-015 | 6, 7 | Planned: deterministic risk boundary and handoff |
| FR-020 | 3, 4 | Planned: catalog query and Telegram pagination |
| FR-021 | 3 | Phase 1 service fields implemented; deterministic query planned |
| FR-022 | 1, 3 | Implemented: price presentation invariants and tests |
| FR-023 | 1, 2, 3 | Active/bookable and snapshot invariants implemented; query enforcement planned |
| FR-030 | 6 | Planned: versioned qualification schemas |
| FR-031 | 6, 7 | Planned: extraction, validation, summary, missing fields |
| FR-032 | 6 | Planned: correction workflow |
| FR-033 | 1, 6 | Deterministic score boundary implemented; configured rules planned |
| FR-034 | 1, 2, 6 | Lead fields/consent invariant implemented; persistence planned |
| FR-035 | 6, 10 | Planned: urgent rules and notifications |
| FR-040 | 3, 5 | UTC-aware foundation implemented; local slot rendering planned |
| FR-041 | 3, 5 | Schedule primitives implemented; availability engine planned |
| FR-042 | 5 | Planned: durable short-lived slot holds |
| FR-043 | 2, 5 | Idempotency value object implemented; atomic confirmation planned |
| FR-044 | 5, 6 | Planned: configured data collection |
| FR-045 | 5 | Planned: immutable review and confirmation token |
| FR-046 | 5 | Planned: cancel/reschedule use cases |
| FR-047 | 1, 2, 5 | Implemented: explicit booking lifecycle and append-only domain history |
| FR-048 | 5, 10 | Planned: post-commit outbox notifications |
| FR-049 | 5, 10 | Planned: hold expiry and cleanup worker |
| FR-050 | 3 | Schedule validation implemented; open/next-open calculation planned |
| FR-051 | 3, 4 | Planned: outside-hours deterministic response |
| FR-052 | 3, 6 | Handoff due-time field implemented; next-open policy planned |
| FR-060 | 4, 9 | Active workflow field implemented; durable memory planned |
| FR-061 | 9 | Planned: facts with provenance/confidence/sensitivity |
| FR-062 | 9 | Planned: confirmation-state enforcement |
| FR-063 | 9 | Planned: summary authority boundary |
| FR-064 | 4, 5, 9 | Planned: workflow cancellation and hold release |
| FR-065 | 9, 11 | Planned: retention and anonymization workflow |
| FR-070 | 4, 6 | Planned: explicit handoff entry point |
| FR-071 | 6, 7 | Handoff reason model implemented; trigger policy planned |
| FR-072 | 2, 6 | Core handoff model implemented; links/persistence planned |
| FR-073 | 6, 10 | Planned: idempotent admin notification |
| FR-074 | 1, 6 | Implemented: conversation generative-reply pause policy |
| FR-075 | 6 | Lifecycle model implemented; authorization/use cases planned |
| FR-076 | 2, 6, 10 | Planned: durable takeover audit events |
| FR-080 | 10 | Planned: notification subscriptions |
| FR-081 | 10, 11 | PII-minimization ADR accepted; payload implementation planned |
| FR-082 | 3, 6, 8, 10 | Planned: protected internal administration APIs |
| FR-083 | 3, 6, 8, 11 | Planned: authentication, authorization, validation, audit |
| FR-084 | 1, 2, 8 | Knowledge lifecycle implemented; ingestion status persistence planned |
| FR-090 | 10 | Domain event envelope implemented; analytics catalog/projection planned |
| FR-091 | 10, 11 | Tenant event context implemented; safe dimensions planned |
| FR-092 | 10, 11 | Planned: protected aggregate endpoints |

## Non-functional and baseline ownership

| Specification area | Current baseline | Next enforcement phase |
|---|---|---:|
| Clean Architecture (6.4, 7.2) | Architecture import tests and ADR 0002 | Every phase |
| Tenant isolation (3.3) | Typed tenant IDs and tenant-scoped repository port | 2 |
| UTC/IANA time (6.4, 8.2) | Aware-time validation and ADR 0003 | 2, 3, 5 |
| PostgreSQL/pgvector (7.3, 9) | Decision recorded only | 2 |
| Transactional outbox (7.3) | Decision recorded only | 2 schema, 10 delivery |
| Privacy/logging (15, 17) | ADR 0004, environment policy, secret scan | 9, 11 |
| CI quality baseline (21, 22) | Ruff, mypy, tests/coverage, build, secret scan | Expanded each phase |
| Docker/runtime (19) | Explicitly deferred | 12 |
