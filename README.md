# AI Telegram Business Assistant

A controlled, tenant-aware business workflow system for Telegram customer support, grounded
knowledge answers, lead qualification, booking, and human handoff.

> **Demo notice:** Northstar Auto Care is a fictional portfolio business. The current repository
> ships with Telegram disabled and no credentials, creates only fictional demo appointments,
> leads, and handoff cases, and contains no real customer data.

## Status

- Phase 0: repository and architecture-decision baseline
- Phase 1: framework-independent domain foundation
- Phase 2: PostgreSQL persistence, migrations, repositories, and fictional demo seed
- Phase 3: validated runtime configuration, public business profile, localized catalog,
  deterministic business-hours engine, and protected internal HTTP API
- Phase 4: English-only aiogram presentation, authenticated webhook, durable update deduplication,
  minimal Telegram identity, signed menus, safe rendering, and development polling
- Phase 5: resource-aware tenant-local availability, durable slot holds and drafts, atomic
  appointment confirmation, cancellation/rescheduling, and English-only Telegram booking
- Phase 6: versioned consent and qualification, deterministic validation/scoring, durable lead
  sessions, business-hours-aware human handoff, staff lifecycle API, and Telegram integration
- Phase 7: provider-neutral AI runtime, strict structured outputs, versioned prompts/model policy,
  confidence gating, metadata-only telemetry, Responses adapter, and deterministic degradation
- Phase 8: tenant-scoped Markdown/FAQ ingestion, OpenAI embeddings boundary, pgvector hybrid
  retrieval, publication/effective-date filters, evidence gating, citations, and safe fallback
- Phase 9: tenant-scoped data classification, versioned retention policies, safe anonymization,
  deliberate deletion workflows, durable action/audit records, and privacy-safe logging
- Phase 10: Celery background workers, database-authoritative outbox dispatch, retry/dead-letter
  notification delivery, scheduled maintenance/re-indexing, and tenant-scoped worker monitoring
- Phase 11: privacy-safe structured logging, correlation propagation, low-cardinality Prometheus
  metrics, feature-aware health/readiness, protected diagnostics, and operational runbooks
- Phase 12: tenant lifecycle, atomic provisioning, tenant members/RBAC, rotating hashed credentials,
  operational entitlements, suspension enforcement, protected administration API, and audit trails
- Phase 13: production hardening, deterministic deployment artifacts, recovery procedures,
  supply-chain gates, and release-candidate certification

The current code is deliberately not a chatbot. Consequential operations belong to validated
application and domain workflows; future AI output remains advisory until it passes structured,
authorization, policy, and evidence validation.

The Northstar portfolio demo is English-only. Unsupported locale requests fall back to English;
the Telegram baseline does not include a language selector or `/language` command.

## Architecture baseline

The product is a modular monolith using Clean Architecture:

```text
presentation -> application <- infrastructure
                    |
                  domain
```

Dependencies point inward. Domain and application modules cannot import FastAPI, aiogram,
SQLAlchemy, Redis, Celery, or OpenAI SDK types. PostgreSQL/pgvector is authoritative,
Redis holds only non-authoritative broker state. PostgreSQL remains authoritative for outbox,
notification delivery, attempts, leases, and dead letters.

See [Architecture overview](docs/architecture/README.md) and the
[ADR index](docs/architecture/decisions.md).

## Safety and privacy boundaries

- Never invent prices, availability, policies, diagnosis, guarantees, or staff commitments.
- AI cannot access storage or providers directly and cannot bypass application validation.
- Tenant scope is explicit on owned records and repository calls.
- Use UTC at rest and tenant IANA timezones at business boundaries.
- Secrets are runtime inputs; raw PII, message text, prompts, and credentials are excluded from
  logs by default.
- Human approval is required before any real deployment privacy, retention, escalation, or
  high-risk wording is presented as compliant policy.

## Local development

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-deps --no-build-isolation --editable .
cp .env.example .env
```

Unit and architecture tests need no external service. Phase 2 integration tests require a real
PostgreSQL database with pgvector; set `TEST_DATABASE_URL`. SQLite is not supported.

Run the complete local gate:

```bash
ruff check .
ruff format --check .
mypy
pytest
detect-secrets-hook --baseline .secrets.baseline $(git ls-files)
python -m build --no-isolation
pip-audit --requirement requirements.lock
python scripts/repository_hygiene.py
```

Optional Git hooks:

```bash
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
pre-commit run --all-files
```

Detailed setup, lock updates, and CI-equivalent commands are in
[Developer workflow](docs/development.md). Configuration ownership is documented in
[Environment and configuration](docs/configuration.md).
Credential behavior and tenant bootstrap are documented in
[Authentication](docs/authentication.md), [tenant provisioning](docs/tenant-provisioning.md), and
[security notes](docs/security.md).

Database migration and fictional demo seed commands are documented in the
[Phase 2 database runbook](docs/operations/database.md).
The protected read-only API and Northstar examples are in the
[Phase 3 API runbook](docs/operations/phase-3-api.md).
Telegram webhook registration, polling, retry, and cleanup operations are in the
[Phase 4 Telegram runbook](docs/operations/phase-4-telegram.md).
Availability rules, booking transactions, expiry, and fictional demo policy are in the
[Phase 5 booking runbook](docs/operations/phase-5-booking.md).
Consent, qualification, lead scoring, and handoff operations are in the
[Phase 6 leads and handoff runbook](docs/operations/phase-6-leads-handoff.md).
Provider configuration, safe degradation, privacy, and telemetry operations are in the
[Phase 7 AI runtime runbook](docs/operations/phase-7-ai-runtime.md).
Knowledge ingestion, publication, hybrid retrieval, citations, and rollback are in the
[Phase 8 knowledge runbook](docs/operations/phase-8-knowledge.md).
Data classification, policy approval, preview, anonymization, and retention execution are in the
[Phase 9 privacy runbook](docs/operations/phase-9-privacy-retention.md).
Background worker startup, queues, retries, dead letters, schedules, and monitoring are in the
[Phase 10 background delivery runbook](docs/operations/phase-10-background-delivery.md).
Health, metrics, SLIs, alerts, and privacy-safe failure triage are in the
[Phase 11 observability runbook](docs/operations/phase-11-observability.md).
Tenant provisioning, lifecycle recovery, members, credentials, and capabilities are in the
[Phase 12 administration runbook](docs/operations/phase-12-tenant-administration.md).
Production deployment, rollback, capacity, and recovery procedures are in the
[Phase 13 deployment runbook](docs/operations/phase-13-deployment.md) and
[recovery runbook](docs/operations/phase-13-recovery.md). Promotion is governed by the
[release checklist](docs/operations/release-checklist.md).

## Repository layout

```text
src/business_assistant/
├── domain/          # Pure entities, policies, events, and value objects
├── application/     # Use-case boundaries and inward-facing ports
├── infrastructure/  # PostgreSQL repositories, Telegram stores, safe logs, and demo seed
├── presentation/    # FastAPI and aiogram adapters, rendering, delivery, and middleware
├── bootstrap/       # HTTP composition roots and explicit polling command
└── config/          # Immutable, validated runtime settings
tests/
├── unit/
├── api/
├── architecture/
└── integration/     # Real PostgreSQL migration/repository/constraint tests
migrations/          # Static Alembic revisions
docs/
└── architecture/
```

## Traceability

- [Full requirements traceability](docs/requirements-traceability.md)
- [Phase 1 traceability](docs/phase-1-traceability.md)
- [Phase 13 traceability](docs/phase-13-traceability.md)
- [Phase 2 traceability](docs/phase-2-traceability.md)
- [Phase 3 traceability](docs/phase-3-traceability.md)
- [Phase 4 traceability](docs/phase-4-traceability.md)
- [Phase 5 traceability](docs/phase-5-traceability.md)
- [Phase 6 traceability](docs/phase-6-traceability.md)
- [Phase 7 traceability](docs/phase-7-traceability.md)
- [Phase 8 traceability](docs/phase-8-traceability.md)
- [Phase 9 traceability](docs/phase-9-traceability.md)
- [Phase 10 traceability](docs/phase-10-traceability.md)
- [Phase 11 traceability](docs/phase-11-traceability.md)
- [Phase 12 traceability](docs/phase-12-traceability.md)

The implementation specification remains the source of truth. Documentation in this repository
records decisions and implementation status; it does not replace the specification.
