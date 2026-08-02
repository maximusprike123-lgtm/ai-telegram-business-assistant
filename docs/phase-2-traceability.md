# Phase 2 traceability

| Phase 2 acceptance area | Implementation | Verification |
|---|---|---|
| Async SQLAlchemy/asyncpg | Infrastructure engine, rows, mappers, repositories | Strict mypy; repository integration tests |
| Alembic from empty DB | Static `0001_phase2` revision | Upgrade/downgrade/upgrade integration test |
| PostgreSQL + pgvector | Extension creation and knowledge vector column | Extension/schema inspection test |
| Tenant isolation | Explicit repository tenant predicates and composite FKs | Cross-tenant read and FK rejection tests |
| Booking correctness | Partial GiST exclusion for assigned active resources | Overlap rejection test |
| Transaction boundary | Shared-session UoW; flush without hidden commit | Commit and implicit rollback tests |
| Idempotency/outbox/audit | Tenant unique keys and foundational tables | Migration schema and constraint tests |
| Northstar seed | Environment guard, fixed IDs, schedule, six services | Complete/idempotent/refusal tests |

Schema-only foundations do not claim later application behavior. Outbox dispatch, slot holds,
Telegram updates, retrieval, AI calls, HTTP endpoints, Redis, and workers remain unimplemented.
