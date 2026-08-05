"""Small structured logger that emits only explicitly allowlisted context."""

import json
import logging
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
    }
)


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        supplied = getattr(record, "safe_context", {})
        context: dict[str, Any] = {
            key: value
            for key, value in supplied.items()
            if key in _SAFE_FIELDS and isinstance(value, (str, int, float, bool, type(None)))
        }
        return json.dumps(
            {"level": record.levelname, "event": record.getMessage(), **context},
            ensure_ascii=True,
            separators=(",", ":"),
        )


def configure_logging(level: str, log_format: str) -> logging.Logger:
    # aiogram's default event logger includes exception strings. The application emits a separate
    # allowlisted failure event, so suppress that unsafe duplicate channel.
    logging.getLogger("aiogram.event").disabled = True
    logger = logging.getLogger("business_assistant.telegram")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(SafeJsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger
