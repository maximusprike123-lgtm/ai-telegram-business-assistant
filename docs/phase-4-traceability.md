# Phase 4 completion traceability

| Phase 4 contract | Implementation and verification anchor |
|---|---|
| aiogram dispatcher, routers, thin handlers | `presentation/telegram/dispatcher.py`; representative update tests |
| Trusted bot-to-tenant binding | immutable configuration, token/bot-ID check, middleware and webhook tests |
| Correlation and safe observability | correlation/dedup middleware, safe JSON formatter, log allowlist test |
| Durable update deduplication | migration 0003, PostgreSQL adapter, lifecycle and eight-way concurrency tests |
| Minimal stable identity | identity use case/store, advisory lock, English fallback and concurrency test |
| English-only commands and menus | `/start`, `/help`, `/catalog`, `/hours`, `/cancel`; paged menus and unknown-text tests |
| Profile/catalog/hours integration | navigation service reuses Phase 3 application queries; navigation tests |
| Signed callback safety | bounded tenant-bound HMAC codec; expiry, shape, tamper, repeat, and recovery tests |
| Safe rendering and delivery | HTML escaping, length splitting, keyboard bounds, edit-to-send fallback tests |
| Authenticated FastAPI webhook | header/path, media type, size, schema, safe 400/401/404/413/415/503 tests |
| Development polling | explicit console command, environment/mode guards, shared dispatcher/runtime |
| Phase 3 preservation | existing protected `/api/v1` suite and OpenAPI generation remain green |

Deliberately deferred: booking and appointment data, availability/holds, real human handoff cases,
AI/free-form answering, Redis, Celery, outbox delivery workers, Telegram admin controls, uploads, and
production Docker/deployment. `/language` is intentionally absent because Northstar is English-only.
