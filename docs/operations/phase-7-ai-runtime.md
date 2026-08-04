# Phase 7 AI runtime runbook

## Safety model

AI is optional and advisory. The runtime supports classification, extraction, rewrite, and summary
tasks but has no database, Telegram, booking, qualification, handoff, retrieval, or tool access.
Strict output validation and a confidence gate run before an advisory result is returned. Existing
application use cases and domain rules remain authoritative.

For the Telegram demo, only validated home, catalog, and business-hours routes are accepted from
AI. All other outcomes use the deterministic unsupported/human-help path. A provider outage cannot
block booking, qualification, callbacks, commands, or staff handoff control.

## Enable locally

Keep AI disabled unless a dedicated non-production credential and explicit model policy are
available. Store the credential only in an ignored `.env` or secret manager.

```bash
AI_ENABLED=true
AI_PROVIDER=openai
AI_ROUTER_MODEL=<approved-router-model>
AI_RESPONSE_MODEL=<approved-response-model>
OPENAI_API_KEY=<secret-manager-value>
```

Set timeout, retries, confidence, token limit, temperature, and cost rates using the documented
`AI_*` variables. `AI_STRUCTURED_OUTPUT_MODE` must remain `strict_json_schema`. `OPENAI_BASE_URL`
defaults to the official HTTPS API. Production rejects an HTTP provider URL.

## Telemetry and incident handling

`ai_operations` contains metadata only: tenant/conversation/correlation IDs, task, provider/model,
prompt/schema versions, status, attempts, latency, input/output token counts, estimated cost, safe
failure code, and timestamp. It intentionally has no prompt, input, output, provider body, API key,
or transcript column.

Safe failure codes are `disabled`, `provider_unavailable`, `rate_limited`, `timeout`,
`invalid_output`, `low_confidence`, `refused`, `cancelled`, and `policy_invalid`. Diagnose from
aggregate metadata and provider-side request IDs available in protected provider tooling; do not
copy customer content or provider responses into logs or tickets. Disable `AI_ENABLED` to force
deterministic behavior immediately. Prompt and policy rollback is a configuration/catalog change,
not a business-code edit.

Configured token rates produce estimates, not invoices. Keep rates at zero if no approved pricing
source and currency policy exists. Retention is controlled by `AI_TELEMETRY_RETENTION_DAYS`; the
scheduled deletion worker remains a later phase.
