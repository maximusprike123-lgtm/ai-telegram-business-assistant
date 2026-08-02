import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from business_assistant.infrastructure.persistence import create_engine, create_session_factory


@pytest.fixture(scope="session")
def postgresql_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    if not value.startswith("postgresql+asyncpg://"):
        pytest.fail("TEST_DATABASE_URL must use postgresql+asyncpg")
    return value


def alembic_config(postgresql_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgresql_url)
    return config


@pytest_asyncio.fixture
async def database(
    migrated_postgresql_url: str,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    engine = create_engine(migrated_postgresql_url)
    factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE tenants RESTART IDENTITY CASCADE"))
    yield engine, factory
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE TABLE tenants RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def migrated_postgresql_url(postgresql_url: str) -> str:
    command.upgrade(alembic_config(postgresql_url), "head")
    return postgresql_url
