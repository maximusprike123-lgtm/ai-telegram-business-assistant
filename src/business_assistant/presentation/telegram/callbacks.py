"""Bounded, versioned, tenant-bound Telegram callback tokens."""

import base64
import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from business_assistant.application.common.ports import Clock
from business_assistant.domain.shared import TenantId

MAX_CALLBACK_BYTES = 64


class CallbackAction(StrEnum):
    HOME = "h"
    CATALOG = "ca"
    CATEGORY = "ct"
    SERVICE = "sv"
    HOURS = "hr"
    PRIVACY = "pr"
    HUMAN = "hu"
    CANCEL = "cx"


@dataclass(frozen=True, slots=True)
class CallbackToken:
    action: CallbackAction
    entity_id: UUID | None
    page: int | None


class CallbackTokenError(ValueError):
    pass


def _base36(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result


def _from_base36(value: str) -> int:
    try:
        return int(value, 36)
    except ValueError as exc:
        raise CallbackTokenError("Callback token has an invalid expiry") from exc


def _encode_uuid(value: UUID) -> str:
    return base64.urlsafe_b64encode(value.bytes).decode("ascii").rstrip("=")


def _decode_uuid(value: str) -> UUID:
    try:
        raw = base64.urlsafe_b64decode(value + "==")
        if len(raw) != 16:
            raise ValueError
        return UUID(bytes=raw)
    except (ValueError, TypeError) as exc:
        raise CallbackTokenError("Callback token has an invalid entity") from exc


class SignedCallbackCodec:
    def __init__(
        self,
        signing_key: str,
        *,
        version: int,
        expiry_seconds: int,
        clock: Clock,
    ) -> None:
        if not signing_key:
            raise ValueError("Callback signing key is required")
        self._key = signing_key.encode()
        self._version = version
        self._expiry_seconds = expiry_seconds
        self._clock = clock

    def encode(
        self,
        tenant_id: TenantId,
        action: CallbackAction,
        entity_id: UUID | None = None,
        page: int | None = None,
    ) -> str:
        if page is not None and not 0 <= page <= 1295:
            raise ValueError("Callback page is out of range")
        expires = int(self._clock.now().timestamp()) + self._expiry_seconds
        entity = _encode_uuid(entity_id) if entity_id is not None else "-"
        if page is not None:
            entity = f"{entity}~{_base36(page)}"
        body = f"{self._version}.{action.value}.{entity}.{_base36(expires)}"
        signature = self._signature(tenant_id, body)
        token = f"{body}.{signature}"
        if len(token.encode()) > MAX_CALLBACK_BYTES:
            raise ValueError("Callback token exceeds Telegram's limit")
        return token

    def decode(self, tenant_id: TenantId, value: str) -> CallbackToken:
        if not value.isascii() or len(value.encode()) > MAX_CALLBACK_BYTES:
            raise CallbackTokenError("Callback token is invalid")
        parts = value.split(".")
        if len(parts) != 5:
            raise CallbackTokenError("Callback token structure is invalid")
        version_text, action_text, entity_text, expiry_text, supplied = parts
        if version_text != str(self._version):
            raise CallbackTokenError("Callback token version is unsupported")
        body = ".".join(parts[:4])
        if not hmac.compare_digest(supplied, self._signature(tenant_id, body)):
            raise CallbackTokenError("Callback token signature is invalid")
        try:
            action = CallbackAction(action_text)
        except ValueError as exc:
            raise CallbackTokenError("Callback action is unsupported") from exc
        if _from_base36(expiry_text) <= int(self._clock.now().timestamp()):
            raise CallbackTokenError("Callback token has expired")
        entity_part, separator, page_text = entity_text.partition("~")
        page = _from_base36(page_text) if separator else None
        if page is not None and not 0 <= page <= 1295:
            raise CallbackTokenError("Callback page is out of range")
        entity_id = None if entity_part == "-" else _decode_uuid(entity_part)
        if action in {CallbackAction.CATEGORY, CallbackAction.SERVICE} and entity_id is None:
            raise CallbackTokenError("Callback entity is required")
        if (
            action not in {CallbackAction.CATEGORY, CallbackAction.SERVICE}
            and entity_id is not None
        ):
            raise CallbackTokenError("Callback entity is not allowed")
        if action not in {CallbackAction.CATALOG, CallbackAction.CATEGORY} and page is not None:
            raise CallbackTokenError("Callback page is not allowed")
        return CallbackToken(action, entity_id, page)

    def _signature(self, tenant_id: TenantId, body: str) -> str:
        value = f"{tenant_id}:{body}".encode()
        digest = hmac.new(self._key, value, hashlib.sha256).digest()[:8]
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
