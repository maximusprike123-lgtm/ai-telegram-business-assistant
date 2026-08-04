# Phase 7 completion traceability

| Phase 7 contract | Implementation and verification anchor |
|---|---|
| Provider-neutral boundary | `application.ai` ports and architecture test blocking provider/HTTP imports |
| Replaceable adapters | Provider registry plus isolated OpenAI Responses adapter and mocked HTTP contract tests |
| Five strict outputs | Exact intent/extraction/classification/rewrite/summary schemas and parser tests |
| Validation pipeline | Strict shape -> application allowlist -> advisory business validator -> existing use case |
| Runtime resilience | Per-attempt timeout, bounded transient retries, cancellation propagation, safe unexpected-error fallback |
| Confidence gate | Per-task external threshold; below-threshold output returns a typed deterministic fallback |
| Prompt versioning | Immutable catalog with ID, version, exact variables, metadata, compatibility, and deprecation |
| Model policies | Provider/model/temperature/tokens/timeout/retries/confidence/mode/cost configuration |
| Feature disable | `AI_ENABLED=false` performs no provider call and retains deterministic routing |
| Safe orchestration | Only home/catalog/hours advisory routes; no tool schema or consequential AI action |
| Telemetry and privacy | Migration 0006 and tenant-scoped metadata-only PostgreSQL adapter; no content columns |
| Telegram degradation | Invalid/low/refused/timeout/rate-limit/unavailable results use the existing safe human fallback |

Deferred: tool calling by explicit Phase 7 scope, RAG/embeddings/knowledge retrieval (Phase 8),
conversation memory (Phase 9), workers/notifications (Phase 10), and deployment hardening (Phase 11+).
