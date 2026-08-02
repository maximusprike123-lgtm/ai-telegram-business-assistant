from datetime import datetime

import pytest

from business_assistant.domain.customers import Customer
from business_assistant.domain.shared import (
    CustomerId,
    Locale,
    PhoneNumber,
    TenantId,
    ValidationError,
)
from business_assistant.domain.tenants import Tenant, TenantStatus


def make_tenant(tenant_id: TenantId, **overrides: object) -> Tenant:
    values: dict[str, object] = {
        "id": tenant_id,
        "slug": "northstar-auto-care",
        "name": "Northstar Auto Care",
        "timezone": "Europe/Moscow",
        "default_locale": Locale.EN,
        "supported_locales": frozenset({Locale.EN, Locale.RU}),
    }
    values.update(overrides)
    return Tenant(**values)  # type: ignore[arg-type]


def test_tenant_validates_locale_timezone_and_slug(tenant_id: TenantId) -> None:
    assert make_tenant(tenant_id).can_process_new_work
    with pytest.raises(ValidationError):
        make_tenant(tenant_id, timezone="Mars/Olympus")
    with pytest.raises(ValidationError):
        make_tenant(tenant_id, slug="North Star")
    with pytest.raises(ValidationError):
        make_tenant(tenant_id, supported_locales=frozenset({Locale.RU}))


def test_tenant_status_controls_new_work(tenant_id: TenantId) -> None:
    tenant = make_tenant(tenant_id)
    tenant.deactivate()
    assert tenant.status is TenantStatus.INACTIVE
    assert not tenant.can_process_new_work
    tenant.activate()
    assert tenant.can_process_new_work


def test_customer_requires_privacy_pair(
    tenant_id: TenantId, customer_id: CustomerId, now: datetime
) -> None:
    with pytest.raises(ValidationError):
        Customer(customer_id, tenant_id, Locale.EN, privacy_notice_version="v1")
    customer = Customer(customer_id, tenant_id, Locale.EN)
    customer.accept_privacy_notice("v1", now)
    assert customer.privacy_accepted_at == now


def test_customer_refuses_contact_before_consent(
    tenant_id: TenantId, customer_id: CustomerId, now: datetime
) -> None:
    customer = Customer(customer_id, tenant_id, Locale.RU)
    phone = PhoneNumber.parse("+7 999 123-45-67")
    with pytest.raises(ValidationError):
        customer.update_phone(phone)
    customer.grant_contact_consent(now)
    customer.update_phone(phone)
    assert customer.phone == phone


def test_customer_rejects_naive_consent(tenant_id: TenantId, customer_id: CustomerId) -> None:
    customer = Customer(customer_id, tenant_id, Locale.EN)
    with pytest.raises(ValidationError):
        customer.grant_contact_consent(datetime(2026, 1, 1))
