# Environment and configuration baseline

`.env.example` is an inventory of future runtime settings, not an active configuration loader.
Phase 0/1 code has no runtime dependency on environment variables.

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
- Empty values in `.env.example` are deliberate safe placeholders.
- Rotate any value immediately if it enters Git history; deleting the current file is not enough.

The fictional demo defaults are not approved legal, privacy, or operational policy for a real
business. A human owner must approve the decisions listed in specification section 29.
