# AI Telegram Business Assistant

Domain foundation for a controlled business workflow system. Northstar Auto Care is a
fictional portfolio demonstration business; this repository does not create real appointments.

Phase 1 contains framework-independent domain models and application ports only. Telegram,
HTTP, databases, Redis, Celery, OpenAI, RAG, and deployment are deliberately deferred to their
roadmap phases.

## Development

Requires Python 3.12 or newer.

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy
pytest
```

See [the Phase 1 traceability note](docs/phase-1-traceability.md) for implemented scope.

