"""Validated process-local correlation context shared by outer adapters."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from uuid import UUID, uuid4

_correlation: ContextVar[str | None] = ContextVar("business_assistant_correlation", default=None)
_SAFE_CORRELATION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def parse_or_create(value: str | UUID | None) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, str) and _SAFE_CORRELATION.fullmatch(value):
        return value
    return str(uuid4())


def current_correlation_id() -> str:
    value = _correlation.get()
    return value if value is not None else str(uuid4())


@contextmanager
def correlation_scope(value: str | UUID | None) -> Iterator[str]:
    correlation_id = parse_or_create(value)
    token: Token[str | None] = _correlation.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _correlation.reset(token)
