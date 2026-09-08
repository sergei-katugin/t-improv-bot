from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import ManualAttendee, Registration, Show, ShowFeedback, User, UserRole
from time_utils import utc_now


@pytest.mark.asyncio
async def test_registration_chats_checkin_access_and_finished_show_reporting():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9300, role=UserRole.organizer)
            viewer = User(telegram_id=9301, role=UserRole.user)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(
                title="Finished", team_name="T", show_date=utc_now() - timedelta(days=2),
                location="V", city="C", max_seats=10, creator_id=owner.id,
                registration_chat_id=-100, registration_chat_title="Chat",
            )
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=1, checked_in_count=2),
                ManualAttendee(show_id=show.id, name="Manual", guests=2, checked_in_count=1),
                ShowFeedback(show_id=show.id, user_id=viewer.id, rating=4),
            ])
            await session.commit()

            chat = SimpleNamespace(id=-200, title="New chat", username="new_chat", type=SimpleNamespace(value="supergroup"))
            saved = await crud.remember_registration_chat(session, owner.id, chat)
            assert saved.title == "New chat"
            chat.title = "Renamed"
            assert (await crud.remember_registration_chat(session, owner.id, chat)).title == "Renamed"
            assert (await crud.get_registration_chats(session, owner.id))[0].chat_id == -200

            invite = await crud.create_checkin_invite(session, show.id)
            assert await crud.consume_checkin_invite(session, invite.token, viewer.id) == show.id
            assert await crud.consume_checkin_invite(session, invite.token, viewer.id) is None
            assert await crud.has_any_checkin_access(session, viewer.id)
            assert await crud.has_checkin_access(session, show.id, viewer.id)

            finished = await crud.list_finished_shows_with_registration_chat(session)
            assert [item.id for item in finished] == [show.id]
            outcome = await crud.get_show_outcome(session, show.id)
            assert outcome == {
                "registered": 5, "cancelled": 0, "arrived": 3,
                "feedback_count": 1, "average_rating": 4.0,
            }
            assert await crud.mark_registration_chat_summary_sent(session, show.id, -100)
            assert not await crud.mark_registration_chat_summary_sent(session, show.id, -100)
            assert await crud.clear_registration_chat_if_matches(session, show.id, -100)
            assert not await crud.clear_registration_chat_if_matches(session, show.id, -100)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_crud_edge_cases_for_registration_waitlist_and_announcements():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9400, role=UserRole.organizer)
            viewer = User(telegram_id=9401, role=UserRole.user)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Future", team_name="T", show_date=utc_now() + timedelta(days=2), location="V", city="C", max_seats=2, max_guests=1, creator_id=owner.id)
            session.add(show); await session.commit(); show_id = show.id

            assert await crud.update_registration_guests_safe(session, show_id, viewer.id, -1) is None
            assert await crud.update_registration_guests_safe(session, show_id, viewer.id, 1) is None
            assert await crud.cancel_registration(session, show_id, viewer.id) is None
            assert await crud.join_waitlist(session, show_id, viewer.id, "Viewer") == (None, 0)
            assert await crud.promote_waitlist(session, show_id) is None

            assert await crud.claim_manual_announcement(session, 99999) is False
            await crud.save_channel_message_id(session, show_id, 55, "manual")
            assert await crud.get_last_channel_message_id(session, show_id) == 55
            await crud.save_channel_message_id(session, show_id, 56, "manual")
            assert await crud.get_last_channel_message_id(session, show_id) == 56
            await crud.mark_feedback_requested(session, [])
    finally:
        await engine.dispose()
