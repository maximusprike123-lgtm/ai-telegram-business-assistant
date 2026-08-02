# ADR 0001: Phase 1 domain foundation

- Status: Accepted
- Date: 2026-08-02

## Context

The implementation specification requires a modular monolith with Clean Architecture. The
target directory had no Phase 0 baseline, code, or Git history when Phase 1 began.

## Decision

Implement the Phase 1 domain as Python 3.12+ modules under `src/business_assistant`. Domain
modules depend only on the standard library. Mutable aggregate roots expose explicit methods
for state changes; immutable value objects validate inputs at construction. Every
business-owned aggregate contains an opaque `TenantId`. Application ports use structural
typing and always require explicit tenant scope. Infrastructure adapters are deferred.

Create only the packaging and test configuration required to exercise Phase 1. Phase 0 CI,
environment configuration, deployment artifacts, and later-phase adapters remain deferred.

## Consequences

- AI or presentation code cannot directly make a booking, lead, handoff, or knowledge state
  transition without passing domain validation.
- Persistence mappings will need to reconstruct these models without weakening invariants.
- Phone normalization intentionally accepts unnormalized values but marks them as such; only
  E.164 values may be marked verified.
- UTC normalization is a persistence responsibility, while the domain rejects naive times.

