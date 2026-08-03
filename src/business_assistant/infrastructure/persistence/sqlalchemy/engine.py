"""Async SQLAlchemy engine and session construction."""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    database_url: str,
    *,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 10,
    connect_timeout_seconds: int = 10,
) -> AsyncEngine:
    if not database_url.startswith("postgresql+asyncpg://"):
        raise ValueError("Phase 2 persistence requires a postgresql+asyncpg URL")
    return create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        connect_args={"timeout": connect_timeout_seconds},
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
