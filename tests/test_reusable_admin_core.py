from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import ManualAttendee, Show, User, UserRole
from time_utils import utc_now


async def _database():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _users(session):
    owner = User(telegram_id=7001, username="owner", first_name="Owner", role=UserRole.organizer)
    viewer = User(telegram_id=7002, username="viewer", first_name="Viewer")
    session.add_all([owner, viewer])
    await session.commit()
    return owner, viewer


@pytest.mark.asyncio
async def test_reusable_show_crud_filters_update_and_delete_dependents():
    engine, sessions = await _database()
    try:
        async with sessions() as session:
            owner, viewer = await _users(session)
            active = await crud.create_show(
                session, title="Active", team_name="Alpha", show_date=utc_now() + timedelta(days=2),
                location="Hall One", location_url="https://maps.example/1", city="Limassol",
                poster_text="Poster", poster_file_id="file", max_seats=20,
                creator_id=owner.id, registrar_id=owner.id, checkin_enabled=True,
                feedback_enabled=True,
            )
            past = await crud.create_show(
                session, title="Past", team_name="Beta", show_date=utc_now() - timedelta(days=2),
                location="Hall Two", city="Nicosia", poster_text=None, poster_file_id=None,
                max_seats=10, creator_id=owner.id,
            )
            cancelled = await crud.create_show(
                session, title="Cancelled", team_name="Alpha", show_date=utc_now() + timedelta(days=3),
                location="Hall One", city="Limassol", poster_text=None, poster_file_id=None,
                max_seats=10, creator_id=owner.id,
            )
            cancelled.is_active = False
            await session.commit()

            assert await crud.has_upcoming_shows(session)
            assert [s.id for s in await crud.list_upcoming_shows(session, city="lim", location="hall one")] == [active.id]
            assert [s.id for s in await crud.list_all_shows(session, status="active")] == [active.id]
            assert [s.id for s in await crud.list_all_shows(session, status="past")] == [past.id]
            assert [s.id for s in await crud.list_all_shows(session, status="cancelled")] == [cancelled.id]
            assert {s.id for s in await crud.list_all_shows(session, team="Alpha")} == {active.id, cancelled.id}
            assert len(await crud.list_all_shows(session, limit=1, offset=1)) == 1
            assert {s.id for s in await crud.list_shows_by_creator(session, owner.telegram_id)} == {
                active.id, past.id, cancelled.id,
            }

            updated = await crud.update_show(session, active.id, title="Updated", max_seats=25)
            assert updated.title == "Updated" and updated.max_seats == 25
            assert await crud.update_show(session, 999999, title="Missing") is None

            await crud.register_user_safe(session, active.id, viewer.id, "Viewer", guests=0)
            await crud.add_manual_attendees(session, active.id, ["Manual"])
            await crud.mark_announcement_sent(session, active.id, "manual", 123)
            loaded = await crud.get_show_with_dependents(session, active.id)
            assert len(loaded.registrations) == 1 and len(loaded.announcement_logs) == 1
            assert await crud.delete_show(session, active.id)
            assert await crud.get_show(session, active.id) is None
            assert not await crud.delete_show(session, active.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reusable_user_roles_lookup_and_menu_flags(monkeypatch):
    engine, sessions = await _database()
    try:
        async with sessions() as session:
            monkeypatch.setattr("config.ADMIN_ID_LIST", [])
            user = await crud.upsert_user(session, 8001, "MixedCase", "First", "Last")
            same = await crud.upsert_user(session, 8001, "renamed", "New", "Last")
            assert same.id == user.id and same.username == "renamed"
            assert (await crud.get_user_by_username(session, "@RENAMED")).id == user.id
            assert (await crud.get_user_by_id(session, user.id)).telegram_id == 8001
            assert await crud.get_user_by_telegram_id(session, 999999) is None

            await crud.mark_onboarding_done(session, 8001)
            await session.refresh(user)
            assert user.onboarding_done
            assert await crud.set_user_role(session, 999999, UserRole.organizer) is None
            await crud.set_user_role(session, 8001, UserRole.organizer)
            assert [u.id for u in await crud.get_all_organizers(session)] == [user.id]

            show = await crud.create_show(
                session, title="Menu", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", poster_text=None, poster_file_id=None,
                max_seats=5, creator_id=user.id,
            )
            assert await crud.get_menu_flags(session, user.id) == (True, False)
            await crud.register_user_safe(session, show.id, user.id, "Viewer", 0)
            assert await crud.has_user_registrations(session, user.id)
            assert await crud.get_menu_flags(session, user.id) == (True, True)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reusable_venues_teams_and_ad_channels_lifecycle():
    engine, sessions = await _database()
    try:
        async with sessions() as session:
            owner, _ = await _users(session)
            await crud.seed_venues(session)
            seeded = await crud.list_venues(session, active_only=False)
            assert len(seeded) == 3
            await crud.seed_venues(session)
            venue = await crud.create_venue(session, "New", "Paphos", None, 60)
            assert (await crud.get_venue(session, venue.id)).default_seats == 60
            await crud.update_venue(session, venue.id, default_seats=70, is_active=False)
            assert venue.id not in {v.id for v in await crud.list_venues(session)}
            assert await crud.update_venue(session, 999999, name="Missing") is None
            await crud.delete_venue(session, venue.id)
            assert await crud.get_venue(session, venue.id) is None

            team = await crud.create_team(session, "Team", "@one", owner.id)
            assert [t.id for t in await crud.list_teams(session, owner.id)] == [team.id]
            await crud.update_team(session, team.id, members="@one, @two")
            assert (await crud.get_team(session, team.id)).members.endswith("@two")
            assert await crud.update_team(session, 999999, name="Missing") is None
            await crud.delete_team(session, team.id)
            assert await crud.get_team(session, team.id) is None

            channel = await crud.add_ad_channel(session, "ExampleChannel")
            assert channel.username == "@examplechannel"
            assert await crud.add_ad_channel(session, "@EXAMPLECHANNEL") is None
            assert [c.id for c in await crud.get_active_ad_channels(session)] == [channel.id]
            toggled = await crud.toggle_ad_channel(session, channel.id)
            assert not toggled.is_active and await crud.get_active_ad_channels(session) == []
            assert await crud.toggle_ad_channel(session, 999999) is None
            assert await crud.delete_ad_channel(session, channel.id)
            assert not await crud.delete_ad_channel(session, channel.id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reusable_attendee_checkin_reminders_and_lists():
    engine, sessions = await _database()
    try:
        async with sessions() as session:
            owner, viewer = await _users(session)
            show = await crud.create_show(
                session, title="Checkin", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", poster_text=None, poster_file_id=None,
                max_seats=10, creator_id=owner.id,
            )
            assert await crud.register_user_safe(session, show.id, viewer.id, "X", 0) is None
            assert await crud.register_user_safe(session, show.id, viewer.id, "Viewer", 51) is None
            reg = await crud.register_user_safe(session, show.id, viewer.id, "Viewer", 1)
            assert [r.id for r in await crud.get_user_registrations(session, viewer.id)] == [reg.id]
            assert [r.id for r in await crud.get_show_registrations(session, show.id)] == [reg.id]
            assert [u.id for u in await crud.get_registered_users_for_show(session, show.id)] == [viewer.id]

            assert await crud.set_reminder_pref(session, show.id, viewer.id, "remind_7d", True)
            due = await crud.get_registrations_for_reminder(session, show.id, 7, limit=10)
            assert [item.id for item in due] == [reg.id]
            await crud.mark_reminded(session, reg.id, 7)
            assert await crud.get_registrations_for_reminder(session, show.id, 7) == []
            await crud.mark_reminded_many(session, [reg.id], 0)
            assert reg.reminded_0d
            assert (await crud.set_confirmed(session, show.id, viewer.id, True)).confirmed is True
            assert await crud.set_confirmed(session, show.id, 999999, True) is None

            await crud.add_manual_attendees(session, show.id, ["Manual"])
            manual = (await crud.get_manual_attendees(session, show.id))[0]
            assert (await crud.toggle_manual_attendee_checkin(session, show.id, manual.id)).checked_in_at
            assert (await crud.set_manual_checkin_count(session, show.id, manual.id, -2)).checked_in_count == 0
            assert await crud.set_manual_checkin_count(session, 999999, manual.id, 1) is None
            assert await crud.toggle_manual_attendee_checkin(session, 999999, manual.id) is None
            assert await crud.delete_manual_attendee(session, manual.id)
            assert not await crud.delete_manual_attendee(session, manual.id)
    finally:
        await engine.dispose()
