# Environment and configuration baseline

`.env.example` is a safe inventory, not a committed runtime configuration. Phase 2 Alembic and
seed commands read `DATABASE_URL`; integration tests read `TEST_DATABASE_URL`. The future
application startup configuration loader remains Phase 3 work.

## Configuration layers

The specification defines four layers, in precedence order:

1. Safe static application defaults.
2. Environment-specific runtime variables.
3. Versioned tenant configuration in PostgreSQL.
4. Feature flags with explicit defaults.

Tenant business policy does not belong in environment variables. Runtime connectivity and
secrets do not belong in tenant configuration.

## Variable ownership

| Group | Examples | Intended owner |
|---|---|---|
| Application | `APP_ENV`, `PUBLIC_BASE_URL` | deployment configuration |
| Demo defaults | tenant slug, timezone, locales | local bootstrap only |
| Telegram | bot and webhook secrets | secret manager/runtime |
| Data services | database, Redis, Celery URLs | deployment/secret manager |
| AI policy | provider key, task models, budgets | secret manager + versioned policy |
| Cryptography | signing and encryption keys | secret manager only |
| Telemetry | log format, OTLP endpoint | deployment configuration |
| Controls | upload, retention, rate limits | environment defaults, then tenant policy |
| Admin bootstrap | local operator token | local demo only |

## Phase 2 database variables

Both database variables must use `postgresql+asyncpg://`; SQLite is rejected. `APP_ENV` must be
`local`, `development`, or `test` for the fictional Northstar seed. Pool settings are inventoried
for the later composition root and are not silently consumed by migration commands.

## Validation policy for later phases

The future configuration adapter must fail startup safely when required values are absent or
incompatible. It must validate environment names, URL schemes, production secret strength,
IANA timezone and locale support, positive limits, polling disabled outside local development,
and model/embedding dimension compatibility. Errors must name the setting without echoing its
secret value.

## Secret handling

- Keep local values in `.env`, which Git ignores.
- Keep staging/production values in the deployment platform's secret manager.
- Never reuse secrets across environments or store them in tenant records, logs, fixtures, CI
  output, screenshots, or model prompts.
- Empty secret values and `change-me` database credentials in `.env.example` are deliberate safe
  placeholders and must never be used as production credentials.
- Rotate any value immediately if it enters Git history; deleting the current file is not enough.

The fictional demo defaults are not approved legal, privacy, or operational policy for a real
business. A human owner must approve the decisions listed in specification section 29.
