import asyncio
import os
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import Show, User
from time_utils import utc_now


def _asyncpg_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://") and "+asyncpg" not in value:
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_requests_cannot_take_the_same_last_seat():
    raw_url = os.getenv("TEST_POSTGRES_URL")
    if not raw_url:
        pytest.skip("TEST_POSTGRES_URL is not configured")
    url = _asyncpg_url(raw_url)
    schema = f"test_capacity_{uuid.uuid4().hex}"
    admin_engine = create_async_engine(url)
    engine = None
    try:
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator = User(telegram_id=9001, first_name="Creator")
            first = User(telegram_id=9002, first_name="First")
            second = User(telegram_id=9003, first_name="Second")
            session.add_all([creator, first, second])
            await session.flush()
            show = Show(
                title="Concurrency", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="Limassol", max_seats=1, creator_id=creator.id,
            )
            session.add(show)
            await session.commit()
            show_id, first_id, second_id = show.id, first.id, second.id

        async def register(user_id, name):
            async with sessions() as session:
                return await crud.register_user_safe(session, show_id, user_id, name, guests=0)

        results = await asyncio.gather(register(first_id, "First"), register(second_id, "Second"))
        assert sum(result is not None for result in results) == 1
        async with sessions() as session:
            assert await crud.count_active_registrations(session, show_id) == 1
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin_engine.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin_engine.dispose()
