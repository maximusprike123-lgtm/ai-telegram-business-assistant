"""Replaceable, tenant-bound static API key adapter for the portfolio internal API."""

import hmac

from business_assistant.application.common.errors import AuthenticationError
from business_assistant.application.common.security import Principal


class StaticApiKeyAuthenticator:
    def __init__(self, expected_key: str, principal: Principal) -> None:
        self._expected_key = expected_key
        self._principal = principal

    def authenticate(self, provided_key: str | None) -> Principal:
        candidate = provided_key or ""
        if not provided_key or not hmac.compare_digest(
            candidate.encode("utf-8"), self._expected_key.encode("utf-8")
        ):
            raise AuthenticationError()
        return self._principal
