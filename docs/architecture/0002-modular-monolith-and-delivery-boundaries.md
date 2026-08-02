# ADR 0002: Modular monolith and delivery boundaries

- Status: Accepted
- Date: 2026-08-02

## Context

The product needs commercial reliability and replaceable integrations without premature
distributed-system complexity. Telegram is one channel and AI is one untrusted provider
capability, not the application core.

## Decision

- Build one modular-monolith codebase with domain, application, infrastructure, presentation,
  bootstrap, and configuration layers.
- Dependencies point inward. Domain and application code do not import framework or provider SDK
  types. Architecture tests enforce this boundary.
- Use explicit CQRS-lite commands and queries through application use cases without separate
  read/write databases.
- Production Telegram delivery uses an authenticated webhook that persists/deduplicates the
  inbound update before returning quickly. Polling is allowed only for local development.
- Deterministic workflows own booking and qualification state. A bounded orchestrator may route
  free text into those workflows but cannot perform consequential state changes directly.
- External providers remain replaceable behind ports. AI output is schema- and policy-validated
  before rendering or use.

## Consequences

- The system can scale API and workers independently while remaining one codebase.
- Presentation and infrastructure changes do not redefine business invariants.
- Local polling is a convenience mode, not a production architecture.
- Adding a provider requires an adapter and contract tests rather than domain imports.
