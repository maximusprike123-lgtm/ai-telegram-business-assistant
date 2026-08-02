"""Validated immutable value objects shared by domain modules."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from .errors import ValidationError
from .identifiers import DocumentId


def ensure_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{field_name} must be timezone-aware")
    return value


class Locale(StrEnum):
    EN = "en"
    RU = "ru"


@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise ValidationError("Money amount must use integer minor units")
        if self.amount_minor < 0:
            raise ValidationError("Money amount cannot be negative")
        currency = self.currency.upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValidationError("Currency must be a three-letter ISO-style code")
        object.__setattr__(self, "currency", currency)


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    raw: str
    normalized_e164: str | None = None
    verified: bool = False

    @classmethod
    def parse(cls, raw: str, *, verified: bool = False) -> "PhoneNumber":
        value = raw.strip()
        if not value or len(value) > 32 or re.search(r"[^0-9+()\-.\s]", value):
            raise ValidationError("Phone number contains invalid characters")
        digits = re.sub(r"\D", "", value)
        normalized = f"+{digits}" if value.startswith("+") and 8 <= len(digits) <= 15 else None
        if len(digits) < 5:
            raise ValidationError("Phone number is too short")
        if verified and normalized is None:
            raise ValidationError("Only an E.164-normalized phone number can be verified")
        return cls(raw=value, normalized_e164=normalized, verified=verified)

    @property
    def is_e164(self) -> bool:
        return self.normalized_e164 is not None


@dataclass(frozen=True, slots=True)
class Confidence:
    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not 0.0 <= self.value <= 1.0:
            raise ValidationError("Confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class TimeRange:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        ensure_aware(self.start, "start")
        ensure_aware(self.end, "end")
        if self.start.astimezone(UTC) >= self.end.astimezone(UTC):
            raise ValidationError("Time range start must precede end")


@dataclass(frozen=True, slots=True)
class Citation:
    document_id: DocumentId
    document_version: int
    chunk_id: str
    score: Confidence
    content_checksum: str

    def __post_init__(self) -> None:
        if self.document_version < 1 or not self.chunk_id.strip():
            raise ValidationError("Citation lineage must identify a document version and chunk")
        if not re.fullmatch(r"[a-fA-F0-9]{32,128}", self.content_checksum):
            raise ValidationError("Citation checksum must be hexadecimal")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    scope: str
    value: str
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.scope.strip() or not self.value.strip() or len(self.value) > 255:
            raise ValidationError("Idempotency key scope and value are required")
        if self.expires_at is not None:
            ensure_aware(self.expires_at, "expires_at")


class PriceMode(StrEnum):
    EXACT = "exact"
    RANGE = "range"
    STARTING_FROM = "starting_from"
    QUOTE_REQUIRED = "quote_required"
    NOT_DISPLAYED = "not_displayed"


@dataclass(frozen=True, slots=True)
class PricePresentation:
    mode: PriceMode
    minimum: Money | None = None
    maximum: Money | None = None

    def __post_init__(self) -> None:
        if self.minimum and self.maximum and self.minimum.currency != self.maximum.currency:
            raise ValidationError("Price range currencies must match")
        match self.mode:
            case PriceMode.EXACT | PriceMode.STARTING_FROM:
                if self.minimum is None or self.maximum is not None:
                    raise ValidationError(f"{self.mode} requires exactly one amount")
            case PriceMode.RANGE:
                if self.minimum is None or self.maximum is None:
                    raise ValidationError("range requires minimum and maximum amounts")
                if self.minimum.amount_minor > self.maximum.amount_minor:
                    raise ValidationError("Price range minimum cannot exceed maximum")
            case PriceMode.QUOTE_REQUIRED | PriceMode.NOT_DISPLAYED:
                if self.minimum is not None or self.maximum is not None:
                    raise ValidationError(f"{self.mode} must not expose an amount")
