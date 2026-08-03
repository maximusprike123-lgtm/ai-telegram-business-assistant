# Developer workflow

## Supported toolchain

- Python 3.12 or newer; CI verifies Python 3.12 and 3.13.
- Git.
- PostgreSQL 18 with pgvector and `btree_gist` is required for the integration gate.
- FastAPI is used only for the protected Phase 3 internal adapter. Redis, Telegram, Celery, and
  OpenAI remain disabled and are not required for tests or local catalog/schedule queries.

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

Focused Phase 3 checks can be run with:

```bash
pytest tests/unit/test_configuration.py tests/unit/test_phase3_queries.py \
  tests/unit/test_schedule_engine.py tests/api
pytest -m postgresql
```

OpenAPI generation is covered by the API tests. To run the fictional demo API, migrate and seed a
local database, set the four `INTERNAL_API_*` variables described in the
[API runbook](operations/phase-3-api.md), and start:

```bash
uvicorn business_assistant.bootstrap.phase3:create_app_from_environment --factory
```

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
