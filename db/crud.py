import secrets
from datetime import datetime, date, timezone
from sqlalchemy import select, func


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Show, Registration, AnnouncementLog, InviteToken, ManualAttendee, UserRole, Venue, Team


# ── Users ──────────────────────────────────────────────────────────────────

async def upsert_user(
    session: AsyncSession,
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None,
) -> User:
    from config import ADMIN_ID_LIST
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        role = UserRole.admin if telegram_id in ADMIN_ID_LIST else UserRole.user
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
        )
        session.add(user)
    else:
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.updated_at = _utcnow()
        if telegram_id in ADMIN_ID_LIST:
            user.role = UserRole.admin
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def mark_onboarding_done(session: AsyncSession, telegram_id: int) -> None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user:
        user.onboarding_done = True
        await session.commit()


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    clean = username.lstrip("@").lower()
    result = await session.execute(
        select(User).where(User.username.ilike(clean))
    )
    return result.scalar_one_or_none()


async def set_user_role(session: AsyncSession, telegram_id: int, role: UserRole) -> User | None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    user.role = role
    await session.commit()
    await session.refresh(user)
    return user


async def get_all_organizers(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).where(User.role.in_([UserRole.organizer, UserRole.admin]))
    )
    return list(result.scalars().all())


# ── Invite tokens ──────────────────────────────────────────────────────────

async def create_invite_token(session: AsyncSession, role: UserRole = UserRole.organizer) -> InviteToken:
    invite = InviteToken(token=secrets.token_urlsafe(16), role=role)
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def consume_invite_token(session: AsyncSession, token: str, user_id: int) -> InviteToken | None:
    result = await session.execute(
        select(InviteToken).where(InviteToken.token == token, InviteToken.used_at.is_(None))
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        return None
    invite.used_at = _utcnow()
    invite.used_by_user_id = user_id
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.role = invite.role
    await session.commit()
    return invite


# ── Shows ──────────────────────────────────────────────────────────────────

async def create_show(
    session: AsyncSession,
    *,
    title: str,
    team_name: str,
    show_date: datetime,
    location: str,
    location_url: str | None = None,
    city: str,
    poster_text: str | None,
    poster_file_id: str | None,
    max_seats: int,
    creator_id: int,
) -> Show:
    show = Show(
        title=title,
        team_name=team_name,
        show_date=show_date,
        location=location,
        location_url=location_url,
        city=city,
        poster_text=poster_text,
        poster_file_id=poster_file_id,
        max_seats=max_seats,
        creator_id=creator_id,
    )
    session.add(show)
    await session.commit()
    await session.refresh(show)
    return show


async def get_show(session: AsyncSession, show_id: int) -> Show | None:
    result = await session.execute(
        select(Show)
        .options(selectinload(Show.creator), selectinload(Show.registrations).selectinload(Registration.user))
        .where(Show.id == show_id)
    )
    return result.scalar_one_or_none()


async def list_upcoming_shows(
    session: AsyncSession,
    city: str | None = None,
    location: str | None = None,
) -> list[Show]:
    query = (
        select(Show)
        .where(Show.show_date >= _utcnow(), Show.is_active == True)
        .order_by(Show.show_date)
    )
    if city:
        query = query.where(Show.city.ilike(f"%{city}%"))
    if location:
        query = query.where(Show.location.ilike(f"%{location}%"))
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_all_shows(
    session: AsyncSession,
    status: str = "all",
    team: str | None = None,
    year: int | None = None,
) -> list[Show]:
    query = select(Show)
    now = _utcnow()
    if status == "active":
        query = query.where(Show.is_active == True, Show.show_date >= now)
    elif status == "past":
        query = query.where(Show.is_active == True, Show.show_date < now)
    elif status == "cancelled":
        query = query.where(Show.is_active == False)
    if team:
        query = query.where(Show.team_name.ilike(f"%{team}%"))
    if year:
        query = query.where(Show.show_date >= datetime(year, 1, 1), Show.show_date < datetime(year + 1, 1, 1))
    result = await session.execute(query.order_by(Show.show_date.desc()))
    return list(result.scalars().all())


async def list_shows_by_creator(session: AsyncSession, telegram_id: int) -> list[Show]:
    result = await session.execute(
        select(Show)
        .join(User, Show.creator_id == User.id)
        .where(User.telegram_id == telegram_id)
        .order_by(Show.show_date.desc())
    )
    return list(result.scalars().all())


async def update_show(session: AsyncSession, show_id: int, **fields) -> Show | None:
    show = await get_show(session, show_id)
    if show is None:
        return None
    for key, value in fields.items():
        setattr(show, key, value)
    show.updated_at = _utcnow()
    await session.commit()
    await session.refresh(show)
    return show


async def count_active_registrations(session: AsyncSession, show_id: int) -> int:
    result = await session.execute(
        select(func.coalesce(func.sum(Registration.guests + 1), 0))
        .where(Registration.show_id == show_id, Registration.is_cancelled == False)
    )
    return result.scalar_one()


# ── Registrations ──────────────────────────────────────────────────────────

async def get_registration(
    session: AsyncSession, show_id: int, user_id: int
) -> Registration | None:
    result = await session.execute(
        select(Registration).where(
            Registration.show_id == show_id,
            Registration.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def register_user_safe(
    session: AsyncSession,
    show_id: int,
    user_id: int,
    attendee_name: str,
    guests: int,
    max_seats: int,
) -> Registration | None:
    """Register a user only if enough seats remain. Re-checks the count atomically
    (as close to the INSERT as possible) to reduce the TOCTOU window."""
    count = await count_active_registrations(session, show_id)
    if count + 1 + guests > max_seats:
        return None
    return await register_user(session, show_id, user_id, attendee_name, guests)


async def register_user(
    session: AsyncSession, show_id: int, user_id: int, attendee_name: str, guests: int = 0
) -> Registration:
    existing = await get_registration(session, show_id, user_id)
    if existing:
        existing.attendee_name = attendee_name
        existing.guests = guests
        existing.is_cancelled = False
        existing.cancelled_at = None
        existing.registered_at = _utcnow()
        existing.reminded_14d = False
        existing.reminded_7d = False
        existing.reminded_1d = False
        await session.commit()
        await session.refresh(existing)
        return existing
    reg = Registration(show_id=show_id, user_id=user_id, attendee_name=attendee_name, guests=guests)
    session.add(reg)
    await session.commit()
    await session.refresh(reg)
    return reg


async def update_registration_guests(
    session: AsyncSession, show_id: int, user_id: int, guests: int
) -> Registration | None:
    reg = await get_registration(session, show_id, user_id)
    if reg is None or reg.is_cancelled:
        return None
    reg.guests = guests
    await session.commit()
    await session.refresh(reg)
    return reg


async def cancel_registration(
    session: AsyncSession, show_id: int, user_id: int
) -> Registration | None:
    reg = await get_registration(session, show_id, user_id)
    if reg is None or reg.is_cancelled:
        return None
    reg.is_cancelled = True
    reg.cancelled_at = _utcnow()
    await session.commit()
    await session.refresh(reg)
    return reg


async def get_user_registrations(session: AsyncSession, user_id: int) -> list[Registration]:
    result = await session.execute(
        select(Registration)
        .join(Show, Registration.show_id == Show.id)
        .options(selectinload(Registration.show))
        .where(
            Registration.user_id == user_id,
            Registration.is_cancelled == False,
            Show.show_date >= _utcnow(),
            Show.is_active == True,
        )
        .order_by(Show.show_date)
    )
    return list(result.scalars().all())


async def get_show_registrations(session: AsyncSession, show_id: int) -> list[Registration]:
    result = await session.execute(
        select(Registration)
        .options(selectinload(Registration.user))
        .where(Registration.show_id == show_id)
        .order_by(Registration.registered_at)
    )
    return list(result.scalars().all())


async def get_registrations_for_reminder(
    session: AsyncSession, show_id: int, days: int
) -> list[Registration]:
    """Active registrations that want a reminder at X days and haven't been reminded yet."""
    want_col = {14: Registration.remind_14d, 7: Registration.remind_7d, 1: Registration.remind_1d}[days]
    sent_col = {14: Registration.reminded_14d, 7: Registration.reminded_7d, 1: Registration.reminded_1d}[days]
    result = await session.execute(
        select(Registration)
        .options(selectinload(Registration.user))
        .where(
            Registration.show_id == show_id,
            Registration.is_cancelled == False,
            want_col == True,
            sent_col == False,
        )
    )
    return list(result.scalars().all())


async def mark_reminded(session: AsyncSession, reg_id: int, days: int) -> None:
    field = {14: "reminded_14d", 7: "reminded_7d", 1: "reminded_1d"}[days]
    result = await session.execute(select(Registration).where(Registration.id == reg_id))
    reg = result.scalar_one_or_none()
    if reg:
        setattr(reg, field, True)
        await session.commit()


async def set_reminder_pref(
    session: AsyncSession, show_id: int, user_id: int, field: str, value: bool
) -> Registration | None:
    reg = await get_registration(session, show_id, user_id)
    if reg is None:
        return None
    setattr(reg, field, value)
    await session.commit()
    await session.refresh(reg)
    return reg


async def get_registered_users_for_show(session: AsyncSession, show_id: int) -> list[User]:
    result = await session.execute(
        select(User)
        .join(Registration, Registration.user_id == User.id)
        .where(
            Registration.show_id == show_id,
            Registration.is_cancelled == False,
        )
    )
    return list(result.scalars().all())


# ── Manual attendees ───────────────────────────────────────────────────────

async def add_manual_attendees(session: AsyncSession, show_id: int, names: list[str]) -> int:
    for name in names:
        session.add(ManualAttendee(show_id=show_id, name=name.strip()))
    await session.commit()
    return len(names)


async def get_manual_attendees(session: AsyncSession, show_id: int) -> list[ManualAttendee]:
    result = await session.execute(
        select(ManualAttendee)
        .where(ManualAttendee.show_id == show_id)
        .order_by(ManualAttendee.added_at)
    )
    return list(result.scalars().all())


async def delete_manual_attendee(session: AsyncSession, attendee_id: int) -> bool:
    result = await session.execute(select(ManualAttendee).where(ManualAttendee.id == attendee_id))
    attendee = result.scalar_one_or_none()
    if attendee is None:
        return False
    await session.delete(attendee)
    await session.commit()
    return True


# ── Announcements ──────────────────────────────────────────────────────────

async def has_announcement_been_sent(
    session: AsyncSession, show_id: int, announcement_type: str
) -> bool:
    result = await session.execute(
        select(AnnouncementLog).where(
            AnnouncementLog.show_id == show_id,
            AnnouncementLog.announcement_type == announcement_type,
        )
    )
    return result.scalar_one_or_none() is not None


async def has_any_announcement_been_sent(session: AsyncSession, show_id: int) -> bool:
    result = await session.execute(
        select(AnnouncementLog).where(AnnouncementLog.show_id == show_id).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def mark_announcement_sent(
    session: AsyncSession, show_id: int, announcement_type: str, channel_message_id: int | None = None
) -> None:
    log = AnnouncementLog(
        show_id=show_id,
        announcement_type=announcement_type,
        channel_message_id=channel_message_id,
    )
    session.add(log)
    await session.commit()


async def save_channel_message_id(
    session: AsyncSession, show_id: int, channel_message_id: int, ann_type: str = "manual"
) -> None:
    result = await session.execute(
        select(AnnouncementLog).where(
            AnnouncementLog.show_id == show_id,
            AnnouncementLog.announcement_type == ann_type,
        )
    )
    log = result.scalar_one_or_none()
    if log:
        log.channel_message_id = channel_message_id
        log.sent_at = _utcnow()
    else:
        session.add(AnnouncementLog(
            show_id=show_id,
            announcement_type=ann_type,
            channel_message_id=channel_message_id,
        ))
    await session.commit()


async def get_last_channel_message_id(session: AsyncSession, show_id: int) -> int | None:
    result = await session.execute(
        select(AnnouncementLog.channel_message_id)
        .where(AnnouncementLog.show_id == show_id, AnnouncementLog.channel_message_id.isnot(None))
        .order_by(AnnouncementLog.sent_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Venues ─────────────────────────────────────────────────────────────────

async def list_venues(session: AsyncSession, active_only: bool = True) -> list[Venue]:
    q = select(Venue).order_by(Venue.id)
    if active_only:
        q = q.where(Venue.is_active == True)
    return list((await session.execute(q)).scalars().all())


async def get_venue(session: AsyncSession, venue_id: int) -> Venue | None:
    return (await session.execute(select(Venue).where(Venue.id == venue_id))).scalar_one_or_none()


async def create_venue(
    session: AsyncSession, name: str, city: str, maps_url: str | None, default_seats: int
) -> Venue:
    venue = Venue(name=name, city=city, maps_url=maps_url, default_seats=default_seats)
    session.add(venue)
    await session.commit()
    await session.refresh(venue)
    return venue


async def update_venue(session: AsyncSession, venue_id: int, **fields) -> Venue | None:
    venue = await get_venue(session, venue_id)
    if venue is None:
        return None
    for k, v in fields.items():
        setattr(venue, k, v)
    await session.commit()
    await session.refresh(venue)
    return venue


async def delete_venue(session: AsyncSession, venue_id: int) -> None:
    venue = await get_venue(session, venue_id)
    if venue:
        await session.delete(venue)
        await session.commit()


async def seed_venues(session: AsyncSession) -> None:
    existing = await list_venues(session, active_only=False)
    if existing:
        return
    for name, city, maps_url, seats in [
        ("Ena Theatre", "Лимасол", "https://maps.app.goo.gl/iEEwHJ5R6x4uhR9V9", 80),
        ("Sinergio",    "Лимасол", "https://maps.app.goo.gl/2rWAhMCTXUdaVnqR7", 70),
        ("KVARTIRNIK",  "Лимасол", "https://maps.app.goo.gl/mokDfc74CCixAsbg8", 40),
    ]:
        session.add(Venue(name=name, city=city, maps_url=maps_url, default_seats=seats))
    await session.commit()


# ── Teams ──────────────────────────────────────────────────────────────────

async def list_teams(session: AsyncSession, user_id: int | None = None) -> list[Team]:
    """user_id=None → all teams (admin); user_id → only that user's teams."""
    q = select(Team).where(Team.is_active == True).order_by(Team.name)
    if user_id is not None:
        q = q.where(Team.creator_id == user_id)
    return list((await session.execute(q)).scalars().all())


async def get_team(session: AsyncSession, team_id: int) -> Team | None:
    return (await session.execute(select(Team).where(Team.id == team_id))).scalar_one_or_none()


async def create_team(session: AsyncSession, name: str, members: str | None, creator_id: int) -> Team:
    team = Team(name=name, members=members, creator_id=creator_id)
    session.add(team)
    await session.commit()
    await session.refresh(team)
    return team


async def update_team(session: AsyncSession, team_id: int, **fields) -> Team | None:
    team = await get_team(session, team_id)
    if team is None:
        return None
    for k, v in fields.items():
        setattr(team, k, v)
    await session.commit()
    await session.refresh(team)
    return team


async def delete_team(session: AsyncSession, team_id: int) -> None:
    team = await get_team(session, team_id)
    if team:
        await session.delete(team)
        await session.commit()
