# Phase 4 Telegram runbook

Northstar Auto Care is fictional and English-only. Use a dedicated demo bot and never place its
token or webhook secrets in Git, shell history, screenshots, URLs, logs, test fixtures, or chat.
Phase 4 shows verified profile, service, and hours data; it does not create appointments or human
handoff cases and does not use AI.

## Migrate and seed

Apply revision `0003_phase4`, then seed Northstar using the existing database runbook:

```bash
alembic upgrade head
python -m business_assistant.infrastructure.persistence.seed
```

The new `telegram_updates` table contains processing metadata only. It never stores update JSON or
message text. Completed and failed rows default to seven-day retention. Until a scheduled cleanup
worker is introduced, an operator may run this bounded maintenance statement after backup policy
review:

```sql
DELETE FROM telegram_updates
WHERE status IN ('completed', 'failed')
  AND created_at < now() - interval '7 days';
```

Never delete current `processing` claims. A failed row is deliberately retryable; a processing row
becomes reclaimable after `TELEGRAM_PROCESSING_STALE_SECONDS`.

## Webhook mode

Set `TELEGRAM_ENABLED=true`, `TELEGRAM_DELIVERY_MODE=webhook`, the bot/token/tenant binding, a public
HTTPS base URL, independent random header and path secrets, and a callback signing key. If the
protected Phase 3 API should also be served, enable its existing tenant-bound credentials.

```bash
uvicorn business_assistant.bootstrap.phase4:create_app_from_environment --factory
```

Controlled application startup calls Telegram `setWebhook` with:

- `https://host/api/v1/webhooks/telegram/<opaque-path-secret>`;
- the configured secret-token header;
- only dispatcher-resolved update types;
- `drop_pending_updates=false`.

Reverse proxies must redact the webhook path and the `X-Telegram-Bot-Api-Secret-Token` header. They
must preserve JSON bodies and return application status codes unchanged. Invalid authentication is
401, an authenticated unknown mapping is 404, malformed input is 400/413/415, completed/duplicate
processing is 200, and transient processing failure is 503 so Telegram can retry.

## Local polling mode

Polling is only for `local`, `development`, or `test`. Set `TELEGRAM_DELIVERY_MODE=polling`; webhook
secrets/base URL are not required. The command explicitly removes an existing webhook without
dropping pending updates, then uses the same dispatcher, identity, deduplication, renderer, and
delivery gateway:

```bash
business-assistant-telegram-polling
```

The command refuses staging/production and cannot be enabled at the same time as webhook delivery.
Stop with SIGINT/SIGTERM; aiogram closes polling and the composition root closes the bot session and
database engine.

## Troubleshooting

- `telegram.webhook_authentication_failed`: verify the secret header outside logs.
- `telegram.bot_mapping_not_found`: verify the configured webhook URL/path and bot deployment.
- `telegram.update_invalid`: compare the received shape with the current Telegram Bot API; do not
  log or persist the raw payload while investigating.
- `telegram.processing_unavailable`: use correlation, tenant, bot, update ID, and safe error type;
  Telegram should retry and the failed/stale claim can be reclaimed.
- An expired or invalid button gives a safe refresh path. Do not disable callback verification.
