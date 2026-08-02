# Phase 1 traceability

| Specification area | Phase 1 implementation |
|---|---|
| Section 6.4 / Clean Architecture | Framework-free domain and boundary import test |
| Section 8.1 | Tenant, Customer, Conversation, Service, Schedule, Booking, Lead, Handoff, Knowledge models |
| Section 8.2 | Opaque IDs, TimeRange, Money, PhoneNumber, Locale, Confidence, Citation, IdempotencyKey, PricePresentation |
| Section 8.3 | Explicit Conversation, Booking, Lead, Handoff, and Knowledge transitions |
| Section 3.3 | `tenant_id` on every business-owned aggregate and tenant-scoped repository port |
| FR-022 | Price mode constructors prohibit inferred or contradictory amounts |
| FR-047 | Booking history is appended on each valid lifecycle transition |
| FR-074 | Conversation exposes a deterministic generative-reply policy |

Not implemented in this phase: persistence, APIs, Telegram, booking availability/holds,
qualification schemas/scoring rules, AI, RAG ingestion/retrieval, workers, notifications,
analytics, Docker, or deployment. Their interfaces and implementations belong to later phases.

