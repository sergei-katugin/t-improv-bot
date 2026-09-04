from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import ManualAttendee, Show, User, UserRole
from time_utils import utc_now


async def _fixture(session):
    creator = User(telegram_id=1001, first_name="Creator")
    viewer = User(telegram_id=1002, first_name="Viewer")
    session.add_all([creator, viewer])
    await session.flush()
    show = Show(
        title="Test", team_name="Team", show_date=utc_now() + timedelta(days=1),
        location="Venue", city="Limassol", max_seats=3, creator_id=creator.id,
    )
    session.add(show)
    await session.commit()
    return creator, viewer, show


@pytest.mark.asyncio
async def test_invite_is_single_use_and_grants_role():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, _ = await _fixture(session)
            invite = await crud.create_invite_token(session, UserRole.organizer)

            assert await crud.consume_invite_token(session, invite.token, viewer.id) is not None
            assert await crud.consume_invite_token(session, invite.token, viewer.id) is None
            await session.refresh(viewer)
            assert viewer.role == UserRole.organizer
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_registration_releases_capacity():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=2)
            assert await crud.count_active_registrations(session, show.id) == 3

            await crud.cancel_registration(session, show.id, viewer.id)

            assert await crud.count_active_registrations(session, show.id) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_data_erasure_deletes_viewer_and_anonymizes_required_creator():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator, viewer, show = await _fixture(session)
            await crud.register_user_safe(session, show.id, viewer.id, "Private Name", guests=0)

            await crud.delete_or_anonymize_user_data(session, viewer)
            assert await session.get(User, viewer.id) is None

            creator_id = creator.id
            await crud.delete_or_anonymize_user_data(session, creator)
            anonymous = await session.get(User, creator_id)
            assert anonymous is not None
            assert anonymous.telegram_id == -creator_id
            assert anonymous.first_name is None
            assert anonymous.username is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkin_toggles_and_feedback_is_updated_not_duplicated():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            registration = await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=0)
            checked = await crud.toggle_registration_checkin(session, show.id, registration.id)
            assert checked.checked_in_at is not None
            unchecked = await crud.toggle_registration_checkin(session, show.id, registration.id)
            assert unchecked.checked_in_at is None

            first = await crud.save_feedback(session, show.id, viewer.id, 3, "ok")
            second = await crud.save_feedback(session, show.id, viewer.id, 5, "great")
            assert first.id == second.id
            assert second.rating == 5
            assert second.comment == "great"
            assert len(await crud.get_show_feedback(session, show.id)) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_feedback_requires_enabled_completed_show_and_issued_request():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            registration = await crud.register_user_safe(
                session, show.id, viewer.id, "Viewer", guests=0,
            )

            assert not await crud.can_submit_feedback(session, show.id, viewer.id)

            show.feedback_enabled = True
            show.show_date = utc_now() - timedelta(hours=3)
            await session.commit()
            assert not await crud.can_submit_feedback(session, show.id, viewer.id)

            await crud.mark_feedback_requested(session, [registration.id])
            assert await crud.can_submit_feedback(session, show.id, viewer.id)

            show.feedback_enabled = False
            await session.commit()
            assert not await crud.can_submit_feedback(session, show.id, viewer.id)

            show.feedback_enabled = True
            show.show_date = utc_now() - timedelta(days=3)
            await session.commit()
            assert not await crud.can_submit_feedback(session, show.id, viewer.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkin_tracks_actual_party_size_counter_and_unique_milestones():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            show.registration_chat_id = -100123
            registration = await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=1)

            updated = await crud.set_registration_checkin_count(session, show.id, registration.id, 3)
            assert updated.checked_in_count == 3  # more people may arrive than booked
            assert updated.checked_in_at is not None

            counter = await crud.change_checkin_counter(session, show.id, -1)
            assert counter.checkin_counter == 0
            counter = await crud.change_checkin_counter(session, show.id, 12)
            assert counter.checkin_counter == 12

            assert await crud.claim_checkin_milestones(session, show.id, 12) == (
                0, 10, -100123, "Test",
            )
            assert await crud.claim_checkin_milestones(session, show.id, 19) is None
            assert await crud.claim_checkin_milestones(session, show.id, 21) == (
                10, 20, -100123, "Test",
            )
            await crud.release_checkin_milestones(session, show.id, 20, 10)
            assert await crud.claim_checkin_milestones(session, show.id, 21) == (
                10, 20, -100123, "Test",
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_checkin_invite_grants_only_scoped_access_and_manual_contact_is_saved():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator, viewer, show = await _fixture(session)
            other_show = Show(
                title="Other", team_name="Team", show_date=utc_now() + timedelta(days=2),
                location="Venue", city="Limassol", max_seats=5, creator_id=creator.id,
            )
            session.add(other_show)
            await session.commit()

            invite = await crud.create_checkin_invite(session, show.id)
            assert await crud.consume_checkin_invite(session, invite.token, viewer.id) == show.id
            assert await crud.consume_checkin_invite(session, invite.token, viewer.id) is None
            assert await crud.has_checkin_access(session, show.id, viewer.id)
            assert not await crud.has_checkin_access(session, other_show.id, viewer.id)

            assert await crud.add_manual_attendees(
                session, show.id, ["Anna"], source="social", contacts=["@anna"],
            ) == 1
            attendee = (await crud.get_manual_attendees(session, show.id))[0]
            assert attendee.contact == "@anna"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upcoming_show_window_manual_reminder_batch_and_announcement_log():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator, _, near = await _fixture(session)
            far = Show(
                title="Far", team_name="Team", show_date=utc_now() + timedelta(days=20),
                location="Venue", city="Limassol", max_seats=5, creator_id=creator.id,
            )
            session.add(far)
            session.add_all([
                ManualAttendee(show_id=near.id, name="First"),
                ManualAttendee(show_id=near.id, name="Second"),
                ManualAttendee(show_id=near.id, name="Done", organizer_reminded_at=utc_now()),
            ])
            await session.commit()

            upcoming = await crud.list_upcoming_shows(
                session, before=utc_now() + timedelta(days=8),
            )
            assert [show.id for show in upcoming] == [near.id]

            pending = await crud.get_pending_manual_attendees_for_reminder(
                session, near.id, limit=1,
            )
            assert [attendee.name for attendee in pending] == ["First"]
            await crud.mark_manual_attendees_reminded(session, [pending[0].id])
            remaining = await crud.get_pending_manual_attendees_for_reminder(session, near.id)
            assert [attendee.name for attendee in remaining] == ["Second"]

            assert not await crud.has_any_announcement_been_sent(session, near.id)
            await crud.mark_announcement_sent(session, near.id, "1d", channel_message_id=123)
            assert await crud.has_announcement_been_sent(session, near.id, "1d")
            assert await crud.has_any_announcement_been_sent(session, near.id)
            assert await crud.get_last_channel_message_id(session, near.id) == 123
            await crud.save_channel_message_id(session, near.id, 456, ann_type="1d")
            assert await crud.get_last_channel_message_id(session, near.id) == 456
    finally:
        await engine.dispose()
