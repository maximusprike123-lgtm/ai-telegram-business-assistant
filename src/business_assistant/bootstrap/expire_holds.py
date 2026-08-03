"""Explicit bounded Phase 5 hold-expiry maintenance command."""

import asyncio

from business_assistant.config import load_settings
from business_assistant.infrastructure.persistence import (
    SQLAlchemyBookingStore,
    create_engine,
    create_session_factory,
)
from business_assistant.infrastructure.system import UTCClock


async def expire() -> int:
    settings = load_settings()
    engine = create_engine(
        settings.database.url,
        pool_size=settings.database.pool_size,
        max_overflow=settings.database.max_overflow,
        connect_timeout_seconds=settings.database.connect_timeout_seconds,
    )
    try:
        store = SQLAlchemyBookingStore(create_session_factory(engine))
        return await store.expire_holds(now=UTCClock().now(), limit=500)
    finally:
        await engine.dispose()


def main() -> None:
    count = asyncio.run(expire())
    print(f"Expired holds: {count}")


if __name__ == "__main__":
    main()
