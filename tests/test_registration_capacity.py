from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import Show, User
from time_utils import utc_now


@pytest.mark.asyncio
async def test_registration_capacity_counts_guests():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator = User(telegram_id=1, first_name="Creator")
            first = User(telegram_id=2, first_name="First")
            second = User(telegram_id=3, first_name="Second")
            session.add_all([creator, first, second])
            await session.flush()
            show = Show(
                title="Test", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="Limassol", max_seats=2, creator_id=creator.id,
            )
            session.add(show)
            await session.commit()

            accepted = await crud.register_user_safe(session, show.id, first.id, "First", guests=1)
            rejected = await crud.register_user_safe(session, show.id, second.id, "Second", guests=0)

            assert accepted is not None
            assert rejected is None
            assert await crud.count_active_registrations(session, show.id) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_attendees_share_the_same_capacity_limit():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator = User(telegram_id=11, first_name="Creator")
            viewer = User(telegram_id=12, first_name="Viewer")
            session.add_all([creator, viewer])
            await session.flush()
            show = Show(
                title="Test", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="Limassol", max_seats=2, creator_id=creator.id,
            )
            session.add(show)
            await session.commit()

            assert await crud.add_manual_attendees(session, show.id, ["Manual"]) == 1
            assert await crud.register_user_safe(
                session, show.id, viewer.id, "Viewer", guests=1,
            ) is None
            assert await crud.count_active_registrations(session, show.id) == 1
    finally:
        await engine.dispose()
