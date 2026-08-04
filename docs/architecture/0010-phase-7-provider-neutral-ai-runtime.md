# ADR 0010: Phase 7 provider-neutral AI runtime

- Status: Accepted
- Date: 2026-08-04

## Context

Phase 6 workflows are deterministic and authoritative. Phase 7 may add language interpretation,
but provider behavior, latency, malformed output, and availability cannot be allowed to redefine
booking, qualification, authorization, consent, or handoff rules. The current phase explicitly
excludes tool calling, RAG, memory, and multi-agent orchestration.

## Decision

- Define provider, prompt, model-policy, telemetry, and business-validation ports in
  `application.ai`. Provider SDK and HTTP types are prohibited from domain and application code.
- Support five bounded tasks: intent, extraction, classification, rewrite, and summary. Every
  result has an exact schema, rejects extra keys and invalid enums/types/bounds, then passes an
  application allowlist and task-specific business validator before use.
- Keep prompts immutable and versioned by identifier/version, with exact variables, schema
  compatibility, metadata, and deprecation state. Keep task model policy external to business
  code, including provider/model, temperature, output limit, timeout, retries, confidence gate,
  strict-output mode, and cost rates.
- Use a bounded runtime for provider lookup, per-attempt timeout, cancellation propagation,
  transient retry, confidence gating, safe failure classification, and deterministic typed
  fallback. Unexpected provider errors also degrade; telemetry failure cannot break a workflow.
- Implement OpenAI as one replaceable infrastructure adapter over the Responses API. Requests use
  strict `text.format` JSON schema, `store=false`, no tools, and separately delimited system/user
  content. Provider bodies, prompt text, credentials, and customer text are never logged or
  persisted.
- Persist one tenant-scoped metadata-only `ai_operations` record per runtime operation. It stores
  task/provider/model/prompt/schema versions, status, attempts, latency, token counts, configured
  cost estimate, safe failure code, correlation, and timestamp.
- Permit validated high-confidence Telegram free text to select existing home, catalog, or hours
  reads. No AI schema contains booking confirmation, mutation, deletion, or direct handoff tools.
  Every other result follows the existing deterministic unsupported/human path.

## Consequences

AI can be disabled without changing customer workflow correctness. Adding another provider
requires an infrastructure adapter and contract tests, not application changes. Cost values are
estimates based on operator-configured rates and are zero until approved rates are supplied.
Provider prompts still receive customer free text when AI is enabled, so the demo disclosure and
privacy copy state that processing boundary. Provider evaluation/calibration, RAG, tools,
conversation memory, and automated background processing remain later work.
