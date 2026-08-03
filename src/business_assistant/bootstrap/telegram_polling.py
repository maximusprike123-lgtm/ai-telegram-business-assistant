"""Explicit local-development polling command; never starts on import."""

import asyncio

from business_assistant.bootstrap.phase4 import build_phase4_components
from business_assistant.config import ConfigurationError, load_settings


async def run() -> None:
    settings = load_settings()
    if settings.application.environment not in {"local", "development", "test"}:
        raise ConfigurationError("APP_ENV", "polling is allowed only in local development")
    if settings.telegram.delivery_mode != "polling":
        raise ConfigurationError("TELEGRAM_DELIVERY_MODE", "must be polling for this command")
    components = build_phase4_components(settings)
    try:
        await components.bot.delete_webhook(drop_pending_updates=False)
        await components.dispatcher.start_polling(
            components.bot,
            allowed_updates=components.dispatcher.resolve_used_update_types(),
            handle_as_tasks=True,
        )
    finally:
        await components.bot.session.close()
        await components.engine.dispose()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
