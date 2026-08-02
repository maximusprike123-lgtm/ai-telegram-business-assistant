# Phase 2 database runbook

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

## Seed the fictional demo

Northstar Auto Care is synthetic portfolio data and creates no real appointments. The seed uses
fixed IDs, is safe to rerun, and refuses production-like environments.

```bash
export APP_ENV=local
python -m business_assistant.infrastructure.persistence.seed
```

It creates the EN/RU tenant, Monday–Saturday workshop schedule, one category, and the six services
specified for Northstar. Prices/durations are clearly synthetic defaults; battery replacement is
quote-based.

## Test

```bash
export TEST_DATABASE_URL='postgresql+asyncpg://app@localhost:5432/business_assistant_test'
pytest
```

CI provisions the pinned `pgvector/pgvector:0.8.2-pg18-trixie` service. Project Dockerfiles and
Compose remain deferred to Phase 12.
