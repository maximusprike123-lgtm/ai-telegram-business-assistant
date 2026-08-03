# ruff: noqa: RUF001
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from tests.helpers_phase3 import FixedClock, phase3_fixture

from business_assistant.application.catalog import GetService, ListServiceCategories, ListServices
from business_assistant.application.common.errors import (
    AuthorizationError,
    CategoryNotFoundError,
    InvalidScheduleError,
    ServiceNotFoundError,
    TenantNotFoundError,
)
from business_assistant.application.common.security import Principal, Role
from business_assistant.application.scheduling import (
    GetBusinessHours,
    GetBusinessStatus,
    GetNextOpening,
)
from business_assistant.application.tenants import GetTenantPublicProfile
from business_assistant.domain.shared import CategoryId, ServiceId, ValidationError


@pytest.mark.asyncio
async def test_catalog_localizes_ru_en_and_falls_back_to_default() -> None:
    uow, principal, _, _ = phase3_fixture()
    categories = ListServiceCategories(lambda: uow)
    assert (await categories.execute(principal, "ru"))[0].name == "Сервис"
    assert (await categories.execute(principal, "en"))[0].name == "Care"
    fallback = await categories.execute(principal, "fr")
    assert fallback[0].locale == "en"
    assert fallback[0].name == "Care"


@pytest.mark.asyncio
async def test_catalog_filters_inactive_content_and_orders_deterministically() -> None:
    uow, principal, _, _ = phase3_fixture()
    result = await ListServices(lambda: uow).execute(principal, "en")
    assert [item.code for item in result] == ["exact", "quote", "starting"]
    category_id = uow.categories.categories[1].id
    filtered = await ListServices(lambda: uow).execute(principal, "en", category_id)
    assert [item.code for item in filtered] == ["exact", "quote", "starting"]
    with pytest.raises(CategoryNotFoundError):
        await ListServices(lambda: uow).execute(principal, "en", CategoryId.new())


@pytest.mark.asyncio
async def test_price_and_duration_wording_are_exact_and_localized() -> None:
    uow, principal, _, _ = phase3_fixture()
    english = await ListServices(lambda: uow).execute(principal, "en")
    russian = await ListServices(lambda: uow).execute(principal, "ru")
    assert {item.code: item.price.display for item in english} == {
        "exact": "RUB 1,250.50",
        "quote": "Contact us for a quote",
        "starting": "From RUB 2,000.00",
    }
    assert {item.code: item.price.display for item in russian} == {
        "exact": "1 250,50 RUB",
        "quote": "Свяжитесь с нами для расчёта стоимости",
        "starting": "От 2 000,00 RUB",
    }
    assert english[0].duration_seconds == 5400
    assert english[0].duration_display == "1 hour 30 minutes"
    assert russian[0].duration_display == "1 час 30 минут"


@pytest.mark.asyncio
async def test_service_not_found_and_insufficient_role_are_explicit() -> None:
    uow, principal, _, _ = phase3_fixture()
    with pytest.raises(ServiceNotFoundError):
        await GetService(lambda: uow).execute(principal, ServiceId.new())
    denied = Principal(principal.subject, principal.tenant_id, Role.KNOWLEDGE_EDITOR)
    with pytest.raises(AuthorizationError):
        await ListServices(lambda: uow).execute(denied)


@pytest.mark.asyncio
async def test_hours_status_next_open_and_profile_use_trusted_tenant() -> None:
    uow, principal, clock, _ = phase3_fixture()
    hours = await GetBusinessHours(lambda: uow).execute(
        principal, date(2026, 12, 31), days=4, locale="ru"
    )
    assert hours[0].closed and hours[0].source == "override"
    assert hours[3].intervals[0].start_local == "10:00"
    status = await GetBusinessStatus(lambda: uow, clock).execute(principal)
    assert status.open_now
    next_opening = await GetNextOpening(
        lambda: uow, FixedClock(datetime(2026, 8, 3, 9, 30, tzinfo=UTC))
    ).execute(principal)
    assert next_opening.next_opening_local is not None
    assert "13:00" in next_opening.next_opening_local
    profile = await GetTenantPublicProfile(lambda: uow, clock).execute(principal, "ru")
    assert profile.description == "Описание"
    assert profile.address == "Демо-адрес"
    assert profile.status.open_now
    assert uow.enter_count == 4


@pytest.mark.asyncio
async def test_cross_tenant_principal_cannot_read_fake_repository_data() -> None:
    uow, principal, _, _ = phase3_fixture()
    other = replace(principal, tenant_id=principal.tenant_id.new())
    with pytest.raises(TenantNotFoundError):
        await ListServices(lambda: uow).execute(other)


@pytest.mark.asyncio
async def test_schedule_timezone_must_match_tenant() -> None:
    uow, principal, clock, _ = phase3_fixture()
    uow.schedules.schedule = replace(uow.schedules.schedule, timezone="America/New_York")
    with pytest.raises(InvalidScheduleError):
        await GetBusinessStatus(lambda: uow, clock).execute(principal)


def test_public_profile_rejects_unsafe_public_contact_values() -> None:
    uow, _, _, _ = phase3_fixture()
    with pytest.raises(ValidationError):
        replace(uow.public_profiles.profile, website_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        replace(uow.public_profiles.profile, public_phone=" ")
