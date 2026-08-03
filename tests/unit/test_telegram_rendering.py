from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest

from business_assistant.application.catalog import (
    PublicPriceDTO,
    ServiceCategoryDTO,
    ServiceDTO,
)
from business_assistant.application.scheduling import (
    BusinessDayDTO,
    BusinessStatusDTO,
    HoursIntervalDTO,
    NextOpeningDTO,
)
from business_assistant.application.tenants import TenantPublicProfileDTO
from business_assistant.domain.shared import TenantId
from business_assistant.presentation.telegram import (
    CallbackAction,
    CallbackTokenError,
    SignedCallbackCodec,
    TelegramRenderer,
)


@dataclass
class MutableClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def callback_codec(clock: MutableClock) -> SignedCallbackCodec:
    return SignedCallbackCodec(
        "unit-test-callback-key",  # pragma: allowlist secret
        version=1,
        expiry_seconds=60,
        clock=clock,
    )


def test_callback_tokens_are_bounded_signed_expiring_and_tenant_bound() -> None:
    clock = MutableClock(datetime(2026, 8, 3, tzinfo=UTC))
    codec = callback_codec(clock)
    tenant = TenantId.new()
    entity = uuid4()
    token = codec.encode(tenant, CallbackAction.SERVICE, entity)
    assert len(token.encode()) <= 64
    assert codec.decode(tenant, token).entity_id == entity
    page_token = codec.encode(tenant, CallbackAction.CATALOG, page=2)
    assert codec.decode(tenant, page_token).page == 2

    with pytest.raises(CallbackTokenError, match="signature"):
        codec.decode(TenantId.new(), token)
    with pytest.raises(CallbackTokenError, match="signature"):
        codec.decode(tenant, token[:-1] + ("A" if token[-1] != "A" else "B"))
    with pytest.raises(CallbackTokenError, match="structure"):
        codec.decode(tenant, "malformed")
    with pytest.raises(CallbackTokenError, match="version"):
        codec.decode(tenant, "2.h.-.0.invalid")
    with pytest.raises(CallbackTokenError, match="invalid"):
        codec.decode(tenant, "x" * 65)

    clock.instant += timedelta(seconds=61)
    with pytest.raises(CallbackTokenError, match="expired"):
        codec.decode(tenant, token)


def test_callback_entity_shapes_are_enforced() -> None:
    clock = MutableClock(datetime(2026, 8, 3, tzinfo=UTC))
    codec = callback_codec(clock)
    tenant = TenantId.new()
    with pytest.raises(CallbackTokenError, match="required"):
        codec.decode(tenant, codec.encode(tenant, CallbackAction.SERVICE))
    with pytest.raises(CallbackTokenError, match="not allowed"):
        codec.decode(tenant, codec.encode(tenant, CallbackAction.HOME, uuid4()))
    with pytest.raises(CallbackTokenError, match="page is not allowed"):
        codec.decode(tenant, codec.encode(tenant, CallbackAction.HOME, page=1))
    with pytest.raises(ValueError, match="page"):
        codec.encode(tenant, CallbackAction.CATALOG, page=1296)


def sample_schedule() -> tuple[tuple[BusinessDayDTO, ...], BusinessStatusDTO, NextOpeningDTO]:
    instant = datetime(2026, 8, 3, 8, tzinfo=UTC)
    days = (
        BusinessDayDTO(
            date(2026, 8, 3),
            0,
            "Monday",
            False,
            (HoursIntervalDTO("08:00", "12:00"), HoursIntervalDTO("13:00", "18:00")),
            "weekly",
            None,
        ),
        BusinessDayDTO(date(2026, 8, 4), 1, "Tuesday", True, (), "override", "Demo closure"),
    )
    status = BusinessStatusDTO(False, instant, date(2026, 8, 3), "11:00", "Europe/Moscow")
    opening = NextOpeningDTO(
        False, instant + timedelta(hours=1), "2026-08-03T12:00+03:00", "Europe/Moscow", 1
    )
    return days, status, opening


def test_renderer_escapes_customer_facing_values_and_builds_safe_navigation() -> None:
    renderer = TelegramRenderer()
    days, status, opening = sample_schedule()
    profile = TenantPublicProfileDTO(
        "Northstar <Demo>",
        "Safe & fictional",
        "en",
        "en",
        ("en",),
        "Europe/Moscow",
        None,
        None,
        None,
        None,
        None,
        None,
        (),
        None,
        None,
        days,
        status,
        opening,
    )
    home = renderer.home(profile)
    assert "Northstar &lt;Demo&gt;" in home.text
    assert "Safe &amp; fictional" in home.text
    assert home.show_reply_menu
    assert "/language" not in home.text

    category = ServiceCategoryDTO(str(uuid4()), "Care <checks>", "en", 0)
    service = ServiceDTO(
        str(uuid4()),
        category.id,
        "inspection",
        "Inspection & test",
        "Checks <verified> items.",
        "en",
        3600,
        "1 hour",
        PublicPriceDTO("quote_required", None, None, None, "Contact us for a quote"),
        "Bring <records>",
        None,
        True,
    )
    assert renderer.catalog((category,)).button_rows[0][0].entity_id == category.id
    assert "Care &lt;checks&gt;" in renderer.services(category, (service,)).text
    detail = renderer.service(service)
    assert "Inspection &amp; test" in detail.text
    assert "Checks &lt;verified&gt; items." in detail.text
    assert "later demo phase" in detail.text
    assert "Next opening" in renderer.hours(days, status, opening).text

    categories = tuple(
        ServiceCategoryDTO(str(uuid4()), f"Category {index}", "en", index) for index in range(7)
    )
    first_page = renderer.catalog(categories)
    assert any(button.label == "Next" for row in first_page.button_rows for button in row)
    second_page = renderer.catalog(categories, 1)
    assert any(button.label == "Previous" for row in second_page.button_rows for button in row)


def test_renderer_static_recovery_pages_are_deterministic_and_english_only() -> None:
    renderer = TelegramRenderer()
    pages = (
        renderer.help(),
        renderer.privacy(),
        renderer.human_placeholder(),
        renderer.cancelled(),
        renderer.unknown(),
        renderer.callback_recovery(),
        renderer.error(),
    )
    assert all(0 < len(page.text) <= 4096 for page in pages)
    assert "does not store message bodies" in renderer.privacy().text
    assert "No request has been created" in renderer.human_placeholder().text
    assert "AI, booking" in renderer.unknown().text


def test_renderer_splits_and_escapes_oversized_plain_text() -> None:
    chunks = TelegramRenderer().split_plain_text(("unsafe <tag> & text " * 600).strip())
    assert len(chunks) > 1
    assert all(0 < len(chunk.text) <= 4096 for chunk in chunks)
    assert all("<tag>" not in chunk.text for chunk in chunks)
    assert TelegramRenderer().split_plain_text("")[0].text == " "
