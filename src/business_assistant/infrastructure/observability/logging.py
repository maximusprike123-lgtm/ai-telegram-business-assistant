"""Structured logger that rejects unsafe events and non-allowlisted context."""

import json
import logging
import re
from typing import Any

_SAFE_FIELDS = frozenset(
    {
        "bot_id",
        "action_id",
        "claim_result",
        "correlation_id",
        "data_class",
        "error_code",
        "error_type",
        "event_type",
        "policy_version",
        "records_affected",
        "result_code",
        "tenant_id",
        "update_id",
        "component",
        "dependency",
        "duration_ms",
        "method",
        "operation",
        "outcome",
        "retry_count",
        "route",
        "slow",
        "status_code",
        "task_name",
    }
)
_SAFE_EVENT = re.compile(r"[a-z][a-z0-9_.-]{0,79}\Z")


def _event(record: logging.LogRecord) -> str:
    value = str(record.msg)
    return value if not record.args and _SAFE_EVENT.fullmatch(value) else "logging.unsafe_event"


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        supplied = getattr(record, "safe_context", {})
        context: dict[str, Any] = {
            key: value
            for key, value in supplied.items()
            if key in _SAFE_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
        }
        return json.dumps(
            {"level": record.levelname, "event": _event(record), **context},
            ensure_ascii=True,
            separators=(",", ":"),
        )


class SafeTextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        supplied = getattr(record, "safe_context", {})
        suffix = " ".join(
            f"{key}={value}"
            for key, value in supplied.items()
            if key in _SAFE_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
        )
        return f"{record.levelname} {_event(record)}" + (f" {suffix}" if suffix else "")


def configure_logging(level: str, log_format: str) -> logging.Logger:
    # aiogram's default event logger includes exception strings. The application emits a separate
    # allowlisted failure event, so suppress that unsafe duplicate channel.
    logging.getLogger("aiogram.event").disabled = True
    logging.getLogger("uvicorn.access").disabled = True
    logger = logging.getLogger("business_assistant")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(SafeJsonFormatter())
    else:
        handler.setFormatter(SafeTextFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
