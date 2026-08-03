"""Stable Phase 3 query, authorization, locale, and schedule errors."""

from dataclasses import dataclass


@dataclass(eq=False)
class ApplicationError(Exception):
    code: str
    safe_message: str

    def __str__(self) -> str:
        return self.safe_message


class TenantNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("tenant.not_found", "Tenant was not found")


class PublicProfileNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("tenant.profile_not_found", "Public business profile is unavailable")


class ServiceNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("catalog.service_not_found", "Service was not found")


class CategoryNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("catalog.category_not_found", "Service category was not found")


class UnresolvedLocaleError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("locale.unresolved", "Localized content is unavailable")


class InvalidScheduleError(ApplicationError):
    def __init__(self, message: str = "Business schedule is invalid") -> None:
        super().__init__("schedule.invalid", message)


class InvalidDateTimeError(ApplicationError):
    def __init__(self, message: str = "A timezone-aware timestamp is required") -> None:
        super().__init__("datetime.invalid", message)


class AuthenticationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("auth.authentication_required", "Valid authentication is required")


class AuthorizationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("auth.forbidden", "This principal is not allowed to perform the action")


class TelegramIdentityUnavailableError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("telegram.identity_unavailable", "Telegram identity is unavailable")


class BookingNotFoundError(ApplicationError):
    def __init__(self) -> None:
        super().__init__("booking.not_found", "Appointment was not found")


class BookingConflictError(ApplicationError):
    def __init__(self, message: str = "That appointment time is no longer available") -> None:
        super().__init__("booking.conflict", message)


class BookingExpiredError(ApplicationError):
    def __init__(self, message: str = "The booking hold or draft has expired") -> None:
        super().__init__("booking.expired", message)


class BookingPolicyError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__("booking.policy", message)
