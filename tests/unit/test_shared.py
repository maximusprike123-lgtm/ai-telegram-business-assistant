from datetime import datetime, timedelta
from typing import cast

import pytest

from business_assistant.domain.shared import (
    AggregateId,
    Citation,
    Confidence,
    DocumentId,
    DomainEvent,
    IdempotencyKey,
    Locale,
    Money,
    PhoneNumber,
    PriceMode,
    PricePresentation,
    TenantId,
    TimeRange,
    ValidationError,
)


def test_opaque_ids_round_trip_and_do_not_cross_compare() -> None:
    tenant_id = TenantId.new()
    assert TenantId.parse(str(tenant_id)) == tenant_id
    assert tenant_id != AggregateId(tenant_id.value)


@pytest.mark.parametrize("amount", [-1, 1.2, True])
def test_money_rejects_invalid_minor_units(amount: object) -> None:
    with pytest.raises(ValidationError):
        Money(amount, "usd")  # type: ignore[arg-type]


def test_money_normalizes_currency() -> None:
    assert Money(1250, "usd") == Money(1250, "USD")


@pytest.mark.parametrize("currency", ["US", "USDD", "12$"])
def test_money_rejects_bad_currency(currency: str) -> None:
    with pytest.raises(ValidationError):
        Money(1, currency)


def test_phone_normalizes_e164_and_preserves_verification() -> None:
    phone = PhoneNumber.parse("+1 (202) 555-0148", verified=True)
    assert phone.normalized_e164 == "+12025550148"
    assert phone.is_e164
    assert phone.verified


def test_phone_accepts_unverified_local_number_without_claiming_e164() -> None:
    phone = PhoneNumber.parse("020 7946 0958")
    assert phone.normalized_e164 is None
    assert not phone.is_e164


@pytest.mark.parametrize("phone", ["abc", "12", "+1 2", "1" * 33])
def test_phone_rejects_invalid_values(phone: str) -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse(phone)


def test_unormalized_phone_cannot_be_verified() -> None:
    with pytest.raises(ValidationError):
        PhoneNumber.parse("020 7946 0958", verified=True)


@pytest.mark.parametrize("value", [-0.1, 1.1, True])
def test_confidence_is_bounded(value: float) -> None:
    with pytest.raises(ValidationError):
        Confidence(value)


def test_time_range_requires_aware_ordered_instants(now: datetime) -> None:
    value = TimeRange(now, now + timedelta(hours=1))
    assert value.end > value.start
    with pytest.raises(ValidationError):
        TimeRange(now.replace(tzinfo=None), now)
    with pytest.raises(ValidationError):
        TimeRange(now, now)


def test_idempotency_key_validates_scope_value_and_expiry(now: datetime) -> None:
    assert IdempotencyKey("booking.confirm", "abc", now).expires_at == now
    with pytest.raises(ValidationError):
        IdempotencyKey("", "abc")
    with pytest.raises(ValidationError):
        IdempotencyKey("scope", "abc", now.replace(tzinfo=None))


def test_citation_preserves_lineage(document_id: DocumentId) -> None:
    citation = Citation(document_id, 2, "chunk-1", Confidence(0.9), "a" * 64)
    assert citation.document_version == 2
    with pytest.raises(ValidationError):
        Citation(document_id, 0, "", Confidence(0.9), "bad")


@pytest.mark.parametrize(
    ("presentation", "valid"),
    [
        (PricePresentation(PriceMode.EXACT, Money(100, "USD")), True),
        (PricePresentation(PriceMode.STARTING_FROM, Money(100, "USD")), True),
        (PricePresentation(PriceMode.RANGE, Money(100, "USD"), Money(200, "USD")), True),
        (PricePresentation(PriceMode.QUOTE_REQUIRED), True),
        (PricePresentation(PriceMode.NOT_DISPLAYED), True),
    ],
)
def test_valid_price_presentations(presentation: PricePresentation, valid: bool) -> None:
    assert valid and isinstance(presentation.mode, PriceMode)


def test_price_modes_reject_contradictory_amounts() -> None:
    with pytest.raises(ValidationError):
        PricePresentation(PriceMode.EXACT)
    with pytest.raises(ValidationError):
        PricePresentation(PriceMode.QUOTE_REQUIRED, Money(100, "USD"))
    with pytest.raises(ValidationError):
        PricePresentation(PriceMode.RANGE, Money(200, "USD"), Money(100, "USD"))
    with pytest.raises(ValidationError):
        PricePresentation(PriceMode.RANGE, Money(100, "USD"), Money(200, "EUR"))


def test_domain_event_is_immutable_and_validated(tenant_id: TenantId, now: datetime) -> None:
    payload = {"locale": Locale.EN}
    event = DomainEvent("tenant.created", tenant_id, "Tenant", tenant_id, now, payload)
    payload["locale"] = cast(Locale, "unsupported")
    assert event.payload["locale"] is Locale.EN
    with pytest.raises(TypeError):
        event.payload["x"] = 1  # type: ignore[index]
    with pytest.raises((ValidationError, ValueError)):
        DomainEvent("", tenant_id, "Tenant", tenant_id, now)
    with pytest.raises((ValidationError, ValueError)):
        DomainEvent("ok", tenant_id, "Tenant", tenant_id, now.replace(tzinfo=None))
