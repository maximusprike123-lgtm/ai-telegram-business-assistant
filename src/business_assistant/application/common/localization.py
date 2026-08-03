"""Deterministic RU/EN content, money, and duration presentation."""

from datetime import timedelta

from business_assistant.domain.shared import Locale, Money, PriceMode, PricePresentation

from .errors import UnresolvedLocaleError


def locale_candidates(
    requested: str | None, default: Locale, supported: frozenset[Locale]
) -> tuple[Locale, ...]:
    candidates: list[Locale] = []
    try:
        parsed = Locale(requested) if requested is not None else default
    except ValueError:
        parsed = default
    for locale in (parsed, default, Locale.EN, *sorted(supported, key=lambda item: item.value)):
        if locale in supported and locale not in candidates:
            candidates.append(locale)
    return tuple(candidates)


def resolve_localized(
    values: dict[Locale, str], candidates: tuple[Locale, ...]
) -> tuple[str, Locale]:
    for locale in candidates:
        value = values.get(locale)
        if value:
            return value, locale
    raise UnresolvedLocaleError()


def resolve_common_locale(
    values: tuple[dict[Locale, str], ...], candidates: tuple[Locale, ...]
) -> Locale:
    for locale in candidates:
        if all(mapping.get(locale) for mapping in values):
            return locale
    raise UnresolvedLocaleError()


def _amount(money: Money, locale: Locale) -> str:
    whole, fraction = divmod(money.amount_minor, 100)
    separator = " " if locale is Locale.RU else ","
    decimal = "," if locale is Locale.RU else "."
    grouped = f"{whole:,}".replace(",", separator)
    return f"{grouped}{decimal}{fraction:02d}"


def format_price(price: PricePresentation, locale: Locale) -> str | None:
    minimum, maximum = price.minimum, price.maximum
    if price.mode is PriceMode.NOT_DISPLAYED:
        return None
    if price.mode is PriceMode.QUOTE_REQUIRED:
        return (
            "Свяжитесь с нами для расчёта стоимости"  # noqa: RUF001
            if locale is Locale.RU
            else "Contact us for a quote"
        )
    if minimum is None:
        raise ValueError("Validated public price is missing its minimum")
    first = _amount(minimum, locale)
    if price.mode is PriceMode.RANGE:
        if maximum is None:
            raise ValueError("Validated price range is missing its maximum")
        amounts = f"{first}-{_amount(maximum, locale)}"
        return (
            f"{amounts} {minimum.currency}"
            if locale is Locale.RU
            else f"{minimum.currency} {amounts}"
        )
    exact = f"{first} {minimum.currency}" if locale is Locale.RU else f"{minimum.currency} {first}"
    if price.mode is PriceMode.STARTING_FROM:
        return f"От {exact}" if locale is Locale.RU else f"From {exact}"
    return exact


def _ru_unit(value: int, forms: tuple[str, str, str]) -> str:
    if value % 10 == 1 and value % 100 != 11:
        return forms[0]
    if 2 <= value % 10 <= 4 and not 12 <= value % 100 <= 14:
        return forms[1]
    return forms[2]


def format_duration(duration: timedelta, locale: Locale) -> str:
    total_minutes = int(duration.total_seconds()) // 60
    hours, minutes = divmod(total_minutes, 60)
    if locale is Locale.RU:
        parts = []
        if hours:
            parts.append(f"{hours} {_ru_unit(hours, ('час', 'часа', 'часов'))}")
        if minutes:
            parts.append(f"{minutes} {_ru_unit(minutes, ('минута', 'минуты', 'минут'))}")
        return " ".join(parts)
    parts = []
    if hours:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
    return " ".join(parts)
