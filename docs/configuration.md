# Environment and configuration baseline

`.env.example` is a safe inventory, not a committed runtime configuration. Phase 4 loads an
immutable `RuntimeSettings` object once at the composition boundary. Domain entities and
application use cases never read process environment variables. Phase 2 Alembic and seed commands
read `DATABASE_URL`; integration tests read `TEST_DATABASE_URL`.

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

## Implemented groups through Phase 5

The loader validates application identity and public URL, PostgreSQL connectivity and bounded
pool settings, internal API bind/timeout settings, tenant-bound API credentials, Telegram,
Redis, Celery and OpenAI enablement, observability, and feature switches. An integration's
credential or URL is required only when that integration is enabled. Telegram is implemented but
disabled by default; Redis, Celery, OpenAI, RAG, and automatic handoff remain unimplemented/off.

Enabled Telegram requires a token, matching numeric bot ID, tenant UUID, callback signing key, and
one delivery mode. Webhook mode additionally requires a public base URL plus independent header and
path secrets limited to Telegram-safe ASCII characters. Polling mode is local-development only.
Payload size, callback version/expiry, terminal-row retention, and stale-processing reclaim time are
bounded. `TELEGRAM_POLLING_ENABLED` is accepted only as a deprecated compatibility input; new
configuration must use `TELEGRAM_DELIVERY_MODE` and cannot select both modes.

Signing/encryption/metrics/admin secrets are optional until their owning feature is used but are
still checked for production strength when supplied. Celery results have an independent switch;
an enabled result policy requires its backend. Enabled OpenAI requires explicit router and
response models; enabled RAG additionally requires an embedding model and bounded dimensions.
Upload, retention, rate, AI iteration/output, logging, and database limits are bounded at startup.
Production rejects message-text logging and the local-only admin bootstrap token.

Phase 5 booking policy is tenant-owned PostgreSQL data, not environment configuration. Northstar's
fictional defaults are a 30-minute slot interval, 30-day horizon, two-hour minimum notice,
five-minute hold, 30-minute draft expiry, and 24-hour cancellation/rescheduling cutoff. Customer
name, phone, and optional-note lengths are also bounded in that record. Real deployments must
replace and approve these values; `.env.example` does not duplicate them.

The protected API requires `INTERNAL_API_ENABLED=true`, a non-empty `INTERNAL_API_KEY`, a UUID
`INTERNAL_API_TENANT_ID`, and a supported `INTERNAL_API_ROLE`. The credential resolves exactly
one trusted principal and tenant; `X-Tenant-ID`, when sent as a defense-in-depth assertion, must
match that tenant. This static adapter is intentionally replaceable and is not a user directory,
OAuth server, key rotation system, or complete SaaS identity provider.

Supported Phase 3 roles are `owner`, `manager`, `agent`, `viewer`, and `knowledge_editor`.
Owner/manager/agent/viewer can read profile, catalog, and schedules. `knowledge_editor` has no
Phase 3 read grant, making authorization tests meaningful without introducing later admin flows.

## Database variables

Both database variables must use `postgresql+asyncpg://`; SQLite is rejected. `APP_ENV` must be
`local`, `development`, or `test` for the fictional Northstar seed. The Phase 3 composition root
applies bounded pool size, overflow, and connection timeout values. Migration commands continue
to own their connection separately.

## Validation policy

Startup fails safely for invalid environment names, schemes/hosts/ports, production HTTP,
weak production credentials, non-IANA timezones, unsupported locales, inconsistent feature
switches, bad roles, bot/token mismatch at composition, and out-of-range numeric settings.
Telegram polling is rejected in production and Telegram webhook URLs must use HTTPS there. Errors
name the setting and a safe reason without echoing its value. Later phases
will add provider-specific model/dimension compatibility checks when the Phase 7 AI adapter owns
a versioned model catalog; Phase 3 already requires and bounds embedding dimensions when RAG is
enabled.

## Secret handling

- Keep local values in `.env`, which Git ignores.
- Keep staging/production values in the deployment platform's secret manager.
- Never reuse secrets across environments or store them in tenant records, logs, fixtures, CI
  output, screenshots, or model prompts.
- Empty secret values in `.env.example` are deliberate safe placeholders and must never be used
  as production credentials. The Northstar tenant UUID is public fictional seed identity, not a
  credential.
- Rotate any value immediately if it enters Git history; deleting the current file is not enough.

The fictional demo defaults are not approved legal, privacy, or operational policy for a real
business. A human owner must approve the decisions listed in specification section 29.
