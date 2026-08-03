import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from business_assistant.infrastructure.persistence import create_engine

pytestmark = pytest.mark.postgresql


def alembic_config(postgresql_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgresql_url)
    return config


def test_initial_migration_round_trips_from_empty_database(postgresql_url: str) -> None:
    config = alembic_config(postgresql_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.mark.asyncio
async def test_schema_has_required_extensions_tables_and_constraints(
    postgresql_url: str,
) -> None:
    engine = create_engine(postgresql_url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
            extensions = set(
                (await connection.scalars(text("SELECT extname FROM pg_extension"))).all()
            )
            exclusion = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'ex_bookings_resource_active_overlap' AND contype = 'x'"
                )
            )
        assert {"vector", "btree_gist"} <= extensions
        assert {
            "tenants",
            "customers",
            "conversations",
            "services",
            "bookings",
            "knowledge_documents",
            "knowledge_chunks",
            "audit_events",
            "outbox_events",
            "tenant_public_profiles",
            "telegram_updates",
        } <= tables
        assert exclusion == 1
    finally:
        await engine.dispose()
