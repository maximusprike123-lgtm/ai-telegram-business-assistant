# Phase 3 completion traceability

| Phase 3 contract | Implementation and verification anchor |
|---|---|
| Immutable validated configuration | `config/settings.py`; configuration unit tests |
| Customer-safe tenant profile | profile domain record, tenant query DTO, migration 0002, API tests |
| English-only active catalog | catalog query use cases, fallback policy, unit and PostgreSQL tests |
| Exact/starting/quote prices and durations | integer-minor-unit DTO mapping and wording tests |
| Weekly hours, gaps, closures, special hours | scheduling engine and deterministic engine tests |
| Current status and bounded next opening | clock-driven use cases; boundary/horizon tests |
| IANA/UTC and DST behavior | configuration and DST/UTC-midnight schedule tests |
| Tenant-scoped persistence | Phase 3 repository ports/adapters, one UoW per query, integration tests |
| Protected versioned HTTP API | explicit FastAPI schemas, `/api/v1`, OpenAPI/API tests |
| Authentication and RBAC | constant-time static-key adapter and auth/tenant mismatch tests |
| Northstar demonstration | idempotent seed profile, six localized services, hours and overrides |

The only schema addition is `tenant_public_profiles`, required because Phase 2 had no
customer-safe profile storage or tenant-constrained choice of public schedule. Revision 0002 is
upgrade/downgrade tested and checked against ORM metadata.

Deferred to Phase 4 and later: Telegram delivery and onboarding, conversational state, AI and
retrieval, booking/availability/holds, lead and handoff workflows, Redis/Celery, notification and
outbox workers, analytics, production deployment, and complete identity management.
