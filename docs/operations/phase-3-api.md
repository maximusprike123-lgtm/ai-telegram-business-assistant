# Phase 3 internal API runbook

This read-only API exposes deterministic public business facts for one authenticated tenant. It
does not connect to Telegram, invoke AI, or create and manage appointments.

## Start the fictional Northstar demo

Migrate and seed as described in the [database runbook](database.md). Then set an ignored local
environment with `INTERNAL_API_ENABLED=true`, a locally generated API key,
`INTERNAL_API_TENANT_ID=f73f5ad0-05c8-5bc6-a2c7-166b959fa73e`, and
`INTERNAL_API_ROLE=viewer`. Never commit the key.

```bash
uvicorn business_assistant.bootstrap.phase3:create_app_from_environment --factory \
  --host 127.0.0.1 --port 8000
```

Send `X-Internal-API-Key` on every request. `X-Tenant-ID` is optional; when present it must equal
the credential-bound tenant. A valid ASCII `X-Request-ID` of 1–128 characters is echoed; otherwise
the server creates a UUID.

## Endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/v1/tenant/profile` | localized customer-safe profile, weekly summary, status, next open |
| `GET /api/v1/catalog/categories` | localized active categories |
| `GET /api/v1/catalog/services` | localized active services; optional `category_id` |
| `GET /api/v1/catalog/services/{service_id}` | one active service |
| `GET /api/v1/business-hours` | `start_date`, 1–31 `days`, and optional locale |
| `GET /api/v1/business-status` | status at optional timezone-aware `at`, otherwise injected clock |
| `GET /api/v1/next-opening` | next opening at optional timezone-aware `at` |

`locale` supports RU and EN. Unsupported requests fall back to tenant default, then EN, then the
lexically first supported locale with content. The resolved locale is returned. OpenAPI is at
`/openapi.json`; interactive docs are at `/docs` for local use.

## Deterministic presentation and schedules

Money remains integer minor units. Exact English/Russian price wording is `RUB 1,250.50` /
`1 250,50 RUB`; starting prices add `From` / `От`; quote-based services say
`Contact us for a quote` / `Свяжитесь с нами для расчёта стоимости`. Durations retain seconds and
have deterministic localized hour/minute wording.

Date overrides replace recurring hours, and closure overrides win by producing a closed day.
Multiple intervals remain separate, so gaps are breaks. Next-open returns `open_now=true` without
searching when currently open, otherwise checks later intervals and subsequent local dates for at
most 370 days. No result inside the horizon is explicit.

Local boundaries use the tenant IANA timezone. A nonexistent spring-forward wall time is rejected.
For repeated fall-back times, opening chooses the earlier instant and closing the later instant.

## Errors and limitations

Errors use `{code, message, correlation_id, details?}`. Authentication is 401, authorization 403,
missing resources 404, invalid input/policy 422, and unexpected failures return a generic 500
without exception text. The static credential adapter is replaceable and deliberately lacks user
accounts, rotation, revocation lists, and OAuth/OIDC. Use TLS and a secret manager outside local
development. Phase 3 does not expose availability or booking endpoints.
