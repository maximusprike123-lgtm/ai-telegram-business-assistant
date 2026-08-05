# syntax=docker/dockerfile:1.7
FROM python:3.13.3-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.lock requirements-build.lock pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --prefix=/runtime --requirement requirements.lock \
    && python -m pip install --requirement requirements-build.lock \
    && python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheels . \
    && python -m pip install --prefix=/runtime --no-deps /wheels/*.whl

FROM python:3.13.3-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN addgroup --system app && adduser --system --ingroup app --home /app app
WORKDIR /app
COPY --from=builder /runtime /usr/local
COPY alembic.ini ./
COPY migrations ./migrations
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2)"
CMD ["uvicorn", "business_assistant.bootstrap.phase3:create_app_from_environment", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--limit-concurrency", "200", "--timeout-keep-alive", "5"]
