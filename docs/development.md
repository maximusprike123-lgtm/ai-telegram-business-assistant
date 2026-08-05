# Developer workflow

## Supported toolchain

- Python 3.12 or newer; CI verifies Python 3.12 and 3.13.
- Git.
- PostgreSQL 18 with pgvector and `btree_gist` is required for the integration gate, Phase 8
  hybrid-retrieval tests, and Phase 9 retention transaction tests.
- FastAPI serves the protected business API and authenticated Telegram webhook. aiogram 3 is the
  Telegram presentation adapter. Phase 5 booking and Phase 6 qualification/handoff transactions
  require PostgreSQL. Phase 7 AI tests use an injected HTTP transport and never require provider
  credentials or network access; Redis, Celery, and AI remain disabled by default.

## First setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.lock
python -m pip install --no-deps --no-build-isolation --editable .
cp .env.example .env
```

The lock file controls CI and local quality-tool versions. The editable install is performed
without dependency or build isolation after the locked Hatchling backend is installed.

## Quality gate

Run these commands from the repository root:

```bash
ruff check .
ruff format --check .
mypy
pytest
detect-secrets-hook --baseline .secrets.baseline $(git ls-files)
python -m build --no-isolation
python -m pip check
```

Set `TEST_DATABASE_URL` to a disposable real PostgreSQL database before `pytest`; the migration
tests upgrade and downgrade its application schema. Never point tests at shared or production data.
The database user must be able to create the `vector` and `btree_gist` extensions.

`pytest` enforces at least 85% overall coverage through `pyproject.toml`. Domain and application
coverage should remain higher where business consequences are involved. Do not lower a gate to
make a change pass.

Focused Phase 3 through Phase 7 checks can be run with:

```bash
pytest tests/unit/test_configuration.py tests/unit/test_phase3_queries.py \
  tests/unit/test_schedule_engine.py tests/unit/test_telegram_application.py \
  tests/unit/test_telegram_rendering.py tests/unit/test_telegram_dispatcher.py tests/api
pytest tests/unit/test_phase6_rules.py tests/integration/test_phase6_qualification.py
pytest tests/unit/test_ai_runtime.py tests/unit/test_openai_adapter.py \
  tests/integration/test_phase7_ai_telemetry.py
pytest tests/unit/test_knowledge.py tests/unit/test_openai_embeddings_adapter.py \
  tests/integration/test_phase8_knowledge.py
pytest tests/unit/test_privacy.py tests/integration/test_phase9_privacy.py
pytest -m postgresql
alembic check
```

OpenAPI generation is covered by the API tests. To run the fictional demo API, migrate and seed a
local database, set the four `INTERNAL_API_*` variables described in the
[API runbook](operations/phase-3-api.md), and start:

```bash
uvicorn business_assistant.bootstrap.phase3:create_app_from_environment --factory
```

After migrating and seeding a disposable database, use the Phase 4 environment inventory and run:

```bash
uvicorn business_assistant.bootstrap.phase4:create_app_from_environment --factory
business-assistant-telegram-polling  # explicit local polling mode only
business-assistant-expire-holds      # bounded manual Phase 5 cleanup
```

The [Telegram runbook](operations/phase-4-telegram.md) documents mutually exclusive modes,
webhook registration, secrets, retry semantics, and update-ledger cleanup.
The [booking runbook](operations/phase-5-booking.md) documents demo policy, transaction guarantees,
manual hold expiry, privacy boundaries, and deferred behavior.
The [Phase 6 runbook](operations/phase-6-leads-handoff.md) documents consent, lead scoring,
handoff pause/control, and the notification delivery boundary.
The [Phase 7 runbook](operations/phase-7-ai-runtime.md) documents the kill switch, provider/model
policy, safe fallbacks, metadata-only telemetry, and rollback.
The [Phase 8 runbook](operations/phase-8-knowledge.md) documents ingestion, publication, retrieval,
evidence thresholds, model changes, and rollback.
The [Phase 9 runbook](operations/phase-9-privacy-retention.md) documents data classifications,
policy approval, safe preview, customer anonymization, retention execution, and limitations.

## Git hooks

```bash
pre-commit install --install-hooks
pre-commit install --hook-type pre-push
```

Commit hooks run secret scanning, Ruff, formatting, and mypy. The pre-push hook also runs the
test suite. CI remains authoritative even when local hooks are not installed.

## Updating dependencies

Dependency ranges live in `pyproject.toml`; reproducible development versions live in
`requirements-dev.lock`.

```bash
python -m pip install 'pip-tools>=7.5,<8'
pip-compile --extra dev --strip-extras --output-file requirements-dev.lock pyproject.toml
python -m pip install --requirement requirements-dev.lock
python -m pip check
```

Review lock changes and rerun the full quality gate. Do not add application dependencies for a
later roadmap phase early.

## Adding code

- Keep dependencies pointing inward.
- Put domain rules in the owning aggregate or policy, not in adapters.
- Require explicit tenant scope for business-owned reads and writes.
- Keep UTC-aware timestamps internally and convert using the tenant timezone at boundaries.
- Add requirement IDs to behavioral tests and update traceability documentation.
- Never commit `.env`, credentials, real PII, provider payloads, or machine-specific paths.
- Keep Alembic revisions static; do not import current metadata from an already-released revision.
