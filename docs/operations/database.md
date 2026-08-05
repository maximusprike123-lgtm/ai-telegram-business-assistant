# Database runbook through Phase 9

Phase 2 supports PostgreSQL only. Use a disposable database for tests; migration tests remove and
recreate the application schema. The database role needs permission to create the `vector` and
`btree_gist` extensions.

## Migrate

Use an async SQLAlchemy URL; keep the populated value in an ignored `.env` or process environment.

```bash
export DATABASE_URL='postgresql+asyncpg://app@localhost:5432/business_assistant'
alembic upgrade head
alembic current
```

Rollback verification for a disposable database:

```bash
alembic downgrade base
alembic upgrade head
```

Downgrade removes application tables but deliberately leaves shared PostgreSQL extensions.
Revision `0003_phase4` adds the metadata-only Telegram update ledger. Its lifecycle and retention
operation are documented in the [Phase 4 Telegram runbook](phase-4-telegram.md).
Revision `0004_phase5` adds booking policy, service/resource eligibility, resource blackout,
draft, and hold tables plus public-reference/identity links on bookings. It is reversible and
validated from an empty database and through a downgrade/upgrade round trip.
Revision `0005_phase6` adds qualification schema/session/consent/update tables, lead completion
snapshots, and linked/idempotent handoff context. It preserves the Phase 2 lead and handoff tables
and extends them through reversible constraints and indexes.
Revision `0006_phase7` adds metadata-only AI operation telemetry. It records tenant/conversation
identity, correlation and version identifiers, status, latency, token counts, cost estimate, and a
safe failure code. Prompts, provider payloads, customer text, and generated text are not stored.
Revision `0007_phase8` preserves normalized source text and adds embedding model, dimensions, and
instruction-risk metadata to knowledge chunks. A database check keeps vectors and their typed
metadata consistent. Hybrid search continues to use the existing GIN full-text index and exact
pgvector cosine search; approximate indexing remains benchmark-driven.
Revision `0008_phase9` creates one versioned retention policy per tenant and immutable completed
privacy-action records. It backfills policies for existing tenants with fictional baseline values;
new tenant provisioning must create a policy explicitly. The revision does not delete or anonymize
business data during migration.

## Seed the fictional demo

Northstar Auto Care is synthetic portfolio data and creates no real appointments. The seed uses
fixed IDs, is safe to rerun, and refuses production-like environments.

```bash
export APP_ENV=local
python -m business_assistant.infrastructure.persistence.seed
```

It creates the English-only tenant and public profile, one category, six services, two fictional
one-capacity service bays, service-to-bay eligibility, and the fictional booking policy
specified for Northstar. Prices/durations are clearly synthetic defaults and exercise exact,
starting-from, and quote-based presentation. Weekdays have 08:00–12:00 and 13:00–18:00
intervals, Saturday is 09:00–15:00, and Sunday is closed. Fixed overrides close 2027-01-01 and
specially open 2027-01-03 from 10:00–14:00. These dates are test/demo fixtures, not current
holiday policy.
The seed also publishes one English `service_request` qualification schema with fictional consent,
score, and structured vehicle-safety routing rules. It does not configure real notification
recipients or approved production emergency policy.
It publishes one English fictional same-day-repair FAQ without making a guarantee. The seed has no
provider credential, so this fixed FAQ is lexical-only; application-ingested sources carry vectors.
It also creates one fictional version-1 retention policy and does not overwrite an operator-updated
policy when the seed is rerun.

## Test

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://app@localhost:5432/business_assistant_test'
pytest
```

CI provisions the pinned `pgvector/pgvector:0.8.2-pg18-trixie` service. Project Dockerfiles and
Compose remain deferred to Phase 12.
