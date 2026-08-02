# AI Telegram Business Assistant

A controlled, tenant-aware business workflow system for Telegram customer support, grounded
knowledge answers, lead qualification, booking, and human handoff.

> **Demo notice:** Northstar Auto Care is a fictional portfolio business. The current repository
> does not connect to Telegram or create real appointments, and it contains no real customer data.

## Status

- Phase 0: repository and architecture-decision baseline
- Phase 1: framework-independent domain foundation
- Phases 2–13: not implemented

The current code is deliberately not a chatbot. Consequential operations belong to validated
application and domain workflows; future AI output remains advisory until it passes structured,
authorization, policy, and evidence validation.

## Architecture baseline

The product is a modular monolith using Clean Architecture:

```text
presentation -> application <- infrastructure
                    |
                  domain
```

Dependencies point inward. Domain and application modules cannot import FastAPI, aiogram,
SQLAlchemy, Redis, Celery, or OpenAI SDK types. PostgreSQL/pgvector will be authoritative,
Redis will hold non-authoritative short-lived state, and background effects will use a
transactional outbox. These components are decisions only until their roadmap phases.

See [Architecture overview](docs/architecture/README.md) and the
[ADR index](docs/architecture/decisions.md).

## Safety and privacy boundaries

- Never invent prices, availability, policies, diagnosis, guarantees, or staff commitments.
- AI cannot access storage or providers directly and cannot bypass application validation.
- Tenant scope is explicit on owned records and repository calls.
- Use UTC at rest and tenant IANA timezones at business boundaries.
- Secrets are runtime inputs; raw PII, message text, prompts, and credentials are excluded from
  logs by default.
- Human approval is required before any real deployment privacy, retention, escalation, or
  high-risk wording is presented as compliant policy.

## Local development

Requires Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-deps --no-build-isolation --editable .
cp .env.example .env
```

Phase 0/1 tests do not require values in `.env` or external services.

Run the complete local gate:

```bash
ruff check .
ruff format --check .
mypy
pytest
detect-secrets-hook --baseline .secrets.baseline $(git ls-files)
python -m build --no-isolation
```

Optional Git hooks:

```bash
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
pre-commit run --all-files
```

Detailed setup, lock updates, and CI-equivalent commands are in
[Developer workflow](docs/development.md). Configuration ownership is documented in
[Environment and configuration](docs/configuration.md).

## Repository layout

```text
src/business_assistant/
├── domain/          # Pure entities, policies, events, and value objects
├── application/     # Use-case boundaries and inward-facing ports
├── infrastructure/  # Replaceable adapters; currently a phase marker only
├── presentation/    # Telegram/HTTP adapters; currently a phase marker only
├── bootstrap/       # Future composition root
└── config/          # Future validated runtime settings boundary
tests/
├── unit/
└── architecture/
docs/
└── architecture/
```

## Traceability

- [Full requirements traceability](docs/requirements-traceability.md)
- [Phase 1 traceability](docs/phase-1-traceability.md)

The implementation specification remains the source of truth. Documentation in this repository
records decisions and implementation status; it does not replace the specification.

