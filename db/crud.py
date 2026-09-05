from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, date, timedelta
from sqlalchemy import select, func, exists, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Show, Registration, ShowFeedback, AnnouncementLog, InviteToken, ManualAttendee, UserRole, Venue, Team, FreeAdChannel, ConnectedRegistrationChat, ShowCheckinStaff, CheckinInviteToken, _utcnow
from app_logging import get_project_logger

logger = get_project_logger(__name__)


async def remember_registration_chat(session: AsyncSession, owner_user_id: int, chat) -> ConnectedRegistrationChat:
    result = await session.execute(select(ConnectedRegistrationChat).where(
        ConnectedRegistrationChat.owner_user_id == owner_user_id,
        ConnectedRegistrationChat.chat_id == chat.id,
    ))
    item = result.scalar_one_or_none()
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or str(chat.id)
    if item is None:
        item = ConnectedRegistrationChat(owner_user_id=owner_user_id, chat_id=chat.id)
        session.add(item)
    item.title = title
    item.username = getattr(chat, "username", None)
    item.chat_type = getattr(getattr(chat, "type", None), "value", None) or str(chat.type)
    item.updated_at = _utcnow()
    await session.commit()
    await session.refresh(item)
    return item


async def get_registration_chats(session: AsyncSession, owner_user_id: int) -> list[ConnectedRegistrationChat]:
    result = await session.execute(
        select(ConnectedRegistrationChat)
        .where(ConnectedRegistrationChat.owner_user_id == owner_user_id)
        .order_by(ConnectedRegistrationChat.updated_at.desc())
        .limit(100)
    )
    return list(result.scalars())


async def create_checkin_invite(session: AsyncSession, show_id: int, ttl_hours: int = 24) -> CheckinInviteToken:
    invite = CheckinInviteToken(
        token=secrets.token_urlsafe(24),
        show_id=show_id,
        expires_at=_utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return invite


async def consume_checkin_invite(session: AsyncSession, token: str, user_id: int) -> int | None:
    result = await session.execute(
        select(CheckinInviteToken)
        .where(
            CheckinInviteToken.token == token,
            CheckinInviteToken.used_at.is_(None),
            CheckinInviteToken.expires_at > _utcnow(),
        )
        .with_for_update()
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        return None
    invite.used_at = _utcnow()
    invite.used_by_user_id = user_id
    show = await session.get(Show, invite.show_id)
    if show is None:
        await session.rollback()
        return None
    exists_result = await session.get(ShowCheckinStaff, (invite.show_id, user_id))
    if exists_result is None:
        session.add(ShowCheckinStaff(
            show_id=invite.show_id,
            user_id=user_id,
            expires_at=max(show.show_date + timedelta(hours=12), _utcnow() + timedelta(hours=12)),
        ))
    await session.commit()
    return invite.show_id


async def has_any_checkin_access(session: AsyncSession, user_id: int) -> bool:
    return bool(await session.scalar(select(exists().where(
        ShowCheckinStaff.user_id == user_id,
        ShowCheckinStaff.expires_at > _utcnow(),
    ))))


async def has_checkin_access(session: AsyncSession, show_id: int, user_id: int) -> bool:
    return bool(await session.scalar(select(exists().where(
        ShowCheckinStaff.show_id == show_id,
        ShowCheckinStaff.user_id == user_id,
        ShowCheckinStaff.expires_at > _utcnow(),
    ))))


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
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            result = await session.execute(select(User).where(User.telegram_id == telegram_id))
            user = result.scalar_one()
        logger.info("created user id=%s telegram_id=%s role=%s", user.id, telegram_id, role)
    else:
        desired_role = UserRole.admin if telegram_id in ADMIN_ID_LIST else user.role
        changed = (
            user.username != username
            or user.first_name != first_name
            or user.last_name != last_name
            or user.role != desired_role
        )
        if changed:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.role = desired_role
            user.updated_at = _utcnow()
            await session.commit()
            logger.info("updated user id=%s telegram_id=%s role=%s", user.id, telegram_id, user.role)
    return user


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def delete_or_anonymize_user_data(session: AsyncSession, user: User) -> bool:
    """Erase user-owned personal data; retain only an anonymous organizer shell if required by history."""
    await session.execute(delete(ShowFeedback).where(ShowFeedback.user_id == user.id))
    await session.execute(delete(Registration).where(Registration.user_id == user.id))
    await session.execute(update(Show).where(Show.registrar_id == user.id).values(registrar_id=None))
    await session.execute(update(InviteToken).where(InviteToken.used_by_user_id == user.id).values(used_by_user_id=None))

    owns_show = await session.scalar(select(exists().where(Show.creator_id == user.id)))
    owns_team = await session.scalar(select(exists().where(Team.creator_id == user.id)))
    if owns_show or owns_team:
        user.telegram_id = -user.id
        user.username = None
        user.first_name = None
        user.last_name = None
        user.role = UserRole.user
        user.onboarding_done = False
    else:
        await session.delete(user)
    await session.commit()
    logger.info("erased personal data for user_id=%s retained_anonymous=%s", user.id, bool(owns_show or owns_team))
    return True


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


async def get_user_by_id(session: AsyncSession, id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.id == id)
    )
    return result.scalar_one_or_none()


async def set_user_role(session: AsyncSession, telegram_id: int, role: UserRole) -> User | None:
    user = await get_user_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    user.role = role
    await session.commit()
    await session.refresh(user)
    logger.info("set user role id=%s telegram_id=%s role=%s", user.id, telegram_id, role)
    return user


async def get_all_organizers(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User).where(User.role.in_([UserRole.organizer, UserRole.admin]))
    )
    return list(result.scalars().all())


# ── Invite tokens ──────────────────────────────────────────────────────────

async def create_invite_token(session: AsyncSession, role: UserRole = UserRole.organizer) -> InviteToken:
    from config import settings
    invite = InviteToken(
        token=secrets.token_urlsafe(32),
        role=role,
        expires_at=_utcnow() + timedelta(hours=settings.INVITE_TTL_HOURS),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    logger.info("created invite token id=%s role=%s", invite.id, invite.role)
    return invite


async def consume_invite_token(session: AsyncSession, token: str, user_id: int) -> InviteToken | None:
    result = await session.execute(
        select(InviteToken)
        .where(
            InviteToken.token == token,
            InviteToken.used_at.is_(None),
            InviteToken.expires_at.is_not(None),
            InviteToken.expires_at > _utcnow(),
        )
        .with_for_update()
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        logger.info("invite token not found, expired, or used user_id=%s", user_id)
        return None
    invite.used_at = _utcnow()
    invite.used_by_user_id = user_id
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user:
        user.role = invite.role
    await session.commit()
    logger.info("consumed invite id=%s by user_id=%s set role=%s", invite.id, user_id, invite.role)
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
    registrar_id: int | None = None,
    registrar_username: str | None = None,
    checkin_enabled: bool = False,
    feedback_enabled: bool = False,
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
        registrar_id=registrar_id,
        registrar_username=registrar_username,
        checkin_enabled=checkin_enabled,
        feedback_enabled=feedback_enabled,
    )
    session.add(show)
    await session.commit()
    await session.refresh(show)
    logger.info(
        "created show id=%s title=%s creator_id=%s registrar_id=%s registrar_username=%s",
        show.id, title, creator_id, show.registrar_id, show.registrar_username,
    )
    return show


async def get_show(session: AsyncSession, show_id: int) -> Show | None:
    result = await session.execute(
        select(Show)
        .options(
            selectinload(Show.creator),
            selectinload(Show.registrar),
        )
        .where(Show.id == show_id)
    )
    return result.scalar_one_or_none()


async def get_show_with_dependents(session: AsyncSession, show_id: int) -> Show | None:
    """Load a show and collections needed by destructive/admin operations."""
    result = await session.execute(
        select(Show)
        .options(
            selectinload(Show.creator),
            selectinload(Show.registrar),
            selectinload(Show.registrations).selectinload(Registration.user),
            selectinload(Show.announcement_logs),
            selectinload(Show.feedback),
        )
        .where(Show.id == show_id)
    )
    return result.scalar_one_or_none()


async def list_upcoming_shows(
    session: AsyncSession,
    city: str | None = None,
    location: str | None = None,
    before: datetime | None = None,
) -> list[Show]:
    query = (
        select(Show)
        .options(selectinload(Show.registrar), selectinload(Show.creator))
        .where(Show.show_date >= _utcnow(), Show.is_active == True)
        .order_by(Show.show_date)
    )
    if city:
        query = query.where(Show.city.ilike(f"%{city}%"))
    if location:
        query = query.where(Show.location.ilike(f"%{location}%"))
    if before is not None:
        query = query.where(Show.show_date < before)
    result = await session.execute(query)
    return list(result.scalars().all())


async def has_upcoming_shows(session: AsyncSession) -> bool:
    result = await session.execute(
        select(exists().where(Show.show_date >= _utcnow(), Show.is_active == True))
    )
    return bool(result.scalar())


async def has_user_registrations(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(
        select(exists().where(
            Registration.user_id == user_id,
            Registration.is_cancelled == False,
            Registration.show_id == Show.id,
            Show.show_date >= _utcnow(),
            Show.is_active == True,
        ))
    )
    return bool(result.scalar())


async def get_menu_flags(session: AsyncSession, user_id: int) -> tuple[bool, bool]:
    has_shows = exists().where(Show.show_date >= _utcnow(), Show.is_active == True)
    has_regs = exists().where(
        Registration.user_id == user_id,
        Registration.is_cancelled == False,
        Registration.show_id == Show.id,
        Show.show_date >= _utcnow(),
        Show.is_active == True,
    )
    row = (await session.execute(select(has_shows, has_regs))).one()
    return bool(row[0]), bool(row[1])


async def list_all_shows(
    session: AsyncSession,
    status: str = "all",
    team: str | None = None,
    year: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[Show]:
    query = select(Show).options(selectinload(Show.registrar), selectinload(Show.creator))
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
    query = query.order_by(Show.show_date.desc()).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def list_shows_by_creator(session: AsyncSession, telegram_id: int) -> list[Show]:
    result = await session.execute(
        select(Show)
        .options(selectinload(Show.registrar), selectinload(Show.creator))
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
    logger.info("updated show id=%s fields=%s", show_id, list(fields.keys()))
    return show


async def deactivate_show(session: AsyncSession, show_id: int) -> bool:
    """Atomically mark an active show as cancelled."""
    show = await session.scalar(select(Show).where(Show.id == show_id).with_for_update())
    if show is None or not show.is_active:
        await session.rollback()
        return False
    show.is_active = False
    await session.commit()
    return True


async def delete_show(session: AsyncSession, show_id: int) -> bool:
    show = await get_show_with_dependents(session, show_id)
    if show is None:
        return False

    try:
        # ORM cascades remove registrations, announcement logs and feedback.
        # Manual attendees do not have a mapped relationship and need an
        # explicit delete.
        manual_attendees = await session.execute(
            select(ManualAttendee).where(ManualAttendee.show_id == show_id)
        )
        for manual_attendee in manual_attendees.scalars().all():
            await session.delete(manual_attendee)

        await session.delete(show)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.exception("failed to delete show id=%s due to DB integrity constraints", show_id)
        return False

    logger.info("deleted show id=%s", show_id)
    return True


async def count_active_registrations(session: AsyncSession, show_id: int) -> int:
    registered_result = await session.execute(
        select(func.coalesce(func.sum(Registration.guests + 1), 0))
        .where(Registration.show_id == show_id, Registration.is_cancelled == False)
    )
    manual_result = await session.execute(
        select(func.count(ManualAttendee.id)).where(ManualAttendee.show_id == show_id)
    )
    return int(registered_result.scalar_one()) + int(manual_result.scalar_one())


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
    source: str | None = None,
) -> Registration | None:
    """Register under a show-row lock so concurrent requests cannot oversubscribe."""
    if guests < 0 or guests > 50 or not 2 <= len(attendee_name.strip()) <= 100:
        return None
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow():
        return None

    existing = await get_registration(session, show_id, user_id)
    count = await count_active_registrations(session, show_id)
    existing_party = 0 if existing is None or existing.is_cancelled else 1 + (existing.guests or 0)
    if count - existing_party + 1 + guests > show.max_seats:
        logger.info("registration prevented by capacity show_id=%s user_id=%s guests=%s count=%s max=%s", show_id, user_id, guests, count, show.max_seats)
        return None

    if existing:
        existing.attendee_name = attendee_name
        existing.guests = guests
        existing.is_cancelled = False
        existing.cancelled_at = None
        existing.registered_at = _utcnow()
        existing.reminded_7d = False
        existing.reminded_2d = False
        existing.reminded_1d = False
        existing.reminded_0d = False
        existing.confirmed = None
        existing.source = source or existing.source
        reg = existing
    else:
        reg = Registration(
            show_id=show_id,
            user_id=user_id,
            attendee_name=attendee_name,
            guests=guests,
            source=source,
        )
        session.add(reg)
    await session.commit()
    await session.refresh(reg)
    return reg


async def update_registration_guests_safe(
    session: AsyncSession, show_id: int, user_id: int, guests: int,
) -> Registration | None:
    if guests < 0 or guests > 50:
        return None
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow():
        return None
    reg = await get_registration(session, show_id, user_id)
    if reg is None or reg.is_cancelled:
        return None
    count = await count_active_registrations(session, show_id)
    old_guests = reg.guests or 0
    if count - (1 + old_guests) + (1 + guests) > show.max_seats:
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
    logger.info("cancelled registration id=%s show_id=%s user_id=%s", reg.id, show_id, user_id)
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
    session: AsyncSession,
    show_id: int,
    days: int,
    *,
    after_id: int = 0,
    limit: int | None = None,
) -> list[Registration]:
    """Active registrations that want a reminder at X days and haven't been reminded yet."""
    sent_col = {
        0: Registration.reminded_0d,
        1: Registration.reminded_1d,
        2: Registration.reminded_2d,
        7: Registration.reminded_7d,
    }[days]
    conditions = [
        Registration.show_id == show_id,
        Registration.id > after_id,
        Registration.is_cancelled == False,
        sent_col == False,
    ]
    if days != 0:
        want_col = {7: Registration.remind_7d, 2: Registration.remind_2d, 1: Registration.remind_1d}[days]
        conditions.append(want_col == True)

    query = (
        select(Registration)
        .options(selectinload(Registration.user))
        .where(*conditions)
        .order_by(Registration.id)
    )
    if limit is not None:
        query = query.limit(limit)
    result = await session.execute(query)
    return list(result.scalars().all())


async def mark_reminded(session: AsyncSession, reg_id: int, days: int) -> None:
    field = {0: "reminded_0d", 1: "reminded_1d", 2: "reminded_2d", 7: "reminded_7d"}[days]
    result = await session.execute(select(Registration).where(Registration.id == reg_id))
    reg = result.scalar_one_or_none()
    if reg:
        setattr(reg, field, True)
        await session.commit()


async def mark_reminded_many(session: AsyncSession, reg_ids: list[int], days: int) -> None:
    if not reg_ids:
        return
    field = {0: "reminded_0d", 1: "reminded_1d", 2: "reminded_2d", 7: "reminded_7d"}[days]
    await session.execute(
        update(Registration)
        .where(Registration.id.in_(reg_ids))
        .values({field: True})
    )
    await session.commit()


async def set_confirmed(
    session: AsyncSession, show_id: int, user_id: int, value: bool | None
) -> Registration | None:
    reg = await get_registration(session, show_id, user_id)
    if reg is None:
        return None
    reg.confirmed = value
    await session.commit()
    await session.refresh(reg)
    return reg


async def toggle_registration_checkin(
    session: AsyncSession, show_id: int, registration_id: int
) -> Registration | None:
    result = await session.execute(
        select(Registration).where(
            Registration.id == registration_id,
            Registration.show_id == show_id,
            Registration.is_cancelled == False,
        )
    )
    reg = result.scalar_one_or_none()
    if reg is None:
        return None
    reg.checked_in_at = None if reg.checked_in_at else _utcnow()
    await session.commit()
    await session.refresh(reg)
    return reg


async def toggle_manual_attendee_checkin(
    session: AsyncSession, show_id: int, attendee_id: int
) -> ManualAttendee | None:
    result = await session.execute(
        select(ManualAttendee).where(
            ManualAttendee.id == attendee_id,
            ManualAttendee.show_id == show_id,
        )
    )
    attendee = result.scalar_one_or_none()
    if attendee is None:
        return None
    attendee.checked_in_at = None if attendee.checked_in_at else _utcnow()
    await session.commit()
    await session.refresh(attendee)
    return attendee


async def set_registration_checkin_count(session: AsyncSession, show_id: int, registration_id: int, count: int) -> Registration | None:
    result = await session.execute(
        select(Registration).where(
            Registration.id == registration_id,
            Registration.show_id == show_id,
            Registration.is_cancelled == False,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    item.checked_in_count = max(0, count)
    item.checked_in_at = _utcnow() if item.checked_in_count else None
    await session.commit()
    await session.refresh(item)
    return item


async def set_manual_checkin_count(session: AsyncSession, show_id: int, attendee_id: int, count: int) -> ManualAttendee | None:
    result = await session.execute(
        select(ManualAttendee).where(
            ManualAttendee.id == attendee_id, ManualAttendee.show_id == show_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None
    item.checked_in_count = max(0, count)
    item.checked_in_at = _utcnow() if item.checked_in_count else None
    await session.commit()
    await session.refresh(item)
    return item


async def change_checkin_counter(session: AsyncSession, show_id: int, delta: int) -> Show | None:
    result = await session.execute(select(Show).where(Show.id == show_id).with_for_update())
    show = result.scalar_one_or_none()
    if show is None:
        return None
    show.checkin_counter = max(0, (show.checkin_counter or 0) + delta)
    await session.commit()
    await session.refresh(show)
    return show


async def claim_checkin_milestones(session: AsyncSession, show_id: int, arrived: int) -> tuple[int, int, int | None, str] | None:
    result = await session.execute(select(Show).where(Show.id == show_id).with_for_update())
    show = result.scalar_one_or_none()
    if show is None or not show.registration_chat_id:
        return None
    previous = show.checkin_milestone or 0
    highest = (arrived // 10) * 10
    if highest <= previous:
        return None
    show.checkin_milestone = highest
    await session.commit()
    return previous, highest, show.registration_chat_id, show.title


async def release_checkin_milestones(
    session: AsyncSession, show_id: int, claimed_highest: int, previous: int
) -> None:
    """Make a failed notification retryable without overwriting a newer claim."""
    await session.execute(
        update(Show)
        .where(Show.id == show_id, Show.checkin_milestone == claimed_highest)
        .values(checkin_milestone=previous)
    )
    await session.commit()


async def get_feedback_candidates(
    session: AsyncSession, *, after_id: int = 0, limit: int = 50
) -> list[Registration]:
    now = _utcnow()
    result = await session.execute(
        select(Registration)
        .join(Show, Registration.show_id == Show.id)
        .options(selectinload(Registration.user), selectinload(Registration.show))
        .where(
            Registration.id > after_id,
            Registration.is_cancelled == False,
            Registration.feedback_requested_at.is_(None),
            Show.feedback_enabled == True,
            Show.show_date <= now - timedelta(hours=2),
            Show.show_date >= now - timedelta(days=2),
        )
        .order_by(Registration.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_feedback_requested(session: AsyncSession, registration_ids: list[int]) -> None:
    if not registration_ids:
        return
    await session.execute(
        update(Registration)
        .where(Registration.id.in_(registration_ids))
        .values(feedback_requested_at=_utcnow())
    )
    await session.commit()


async def can_submit_feedback(session: AsyncSession, show_id: int, user_id: int) -> bool:
    """Return whether this user currently has an issued feedback request."""
    now = _utcnow()
    result = await session.scalar(
        select(exists().where(
            Registration.show_id == show_id,
            Registration.user_id == user_id,
            Registration.is_cancelled == False,
            Registration.feedback_requested_at.is_not(None),
            Show.id == Registration.show_id,
            Show.feedback_enabled == True,
            Show.show_date <= now - timedelta(hours=2),
            Show.show_date >= now - timedelta(days=2),
        ))
    )
    return bool(result)


async def save_feedback(
    session: AsyncSession,
    show_id: int,
    user_id: int,
    rating: int,
    comment: str | None = None,
) -> ShowFeedback:
    identity = (
        ShowFeedback.show_id == show_id,
        ShowFeedback.user_id == user_id,
    )
    values: dict[str, object] = {"rating": rating}
    if comment is not None:
        values["comment"] = comment

    result = await session.execute(
        update(ShowFeedback)
        .where(*identity)
        .values(**values)
    )
    if result.rowcount == 0:
        feedback = ShowFeedback(show_id=show_id, user_id=user_id, rating=rating, comment=comment)
        session.add(feedback)
        try:
            await session.commit()
        except IntegrityError:
            # Another webhook inserted the same feedback between UPDATE and INSERT.
            await session.rollback()
            retry = await session.execute(update(ShowFeedback).where(*identity).values(**values))
            if retry.rowcount == 0:
                raise
            await session.commit()
    else:
        await session.commit()

    feedback = (await session.execute(
        select(ShowFeedback).where(
            ShowFeedback.show_id == show_id,
            ShowFeedback.user_id == user_id,
        )
    )).scalar_one()
    return feedback


async def get_show_feedback(session: AsyncSession, show_id: int) -> list[ShowFeedback]:
    result = await session.execute(
        select(ShowFeedback)
        .options(selectinload(ShowFeedback.user))
        .where(ShowFeedback.show_id == show_id)
        .order_by(ShowFeedback.created_at)
    )
    return list(result.scalars().all())


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

async def add_manual_attendees(
    session: AsyncSession,
    show_id: int,
    names: list[str],
    source: str | None = "manual",
    contacts: list[str | None] | None = None,
) -> int:
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow():
        return 0
    occupied = await count_active_registrations(session, show_id)
    if occupied + len(names) > show.max_seats:
        return 0
    normalized_contacts = contacts or [None] * len(names)
    for name, contact in zip(names, normalized_contacts):
        session.add(ManualAttendee(
            show_id=show_id,
            name=name.strip(),
            contact=contact.strip() if contact and contact.strip() else None,
            source=source,
        ))
    await session.commit()
    return len(names)


async def get_manual_attendees(session: AsyncSession, show_id: int) -> list[ManualAttendee]:
    result = await session.execute(
        select(ManualAttendee)
        .where(ManualAttendee.show_id == show_id)
        .order_by(ManualAttendee.added_at)
    )
    return list(result.scalars().all())


async def get_pending_manual_attendees_for_reminder(
    session: AsyncSession, show_id: int, *, limit: int = 100
) -> list[ManualAttendee]:
    result = await session.execute(
        select(ManualAttendee)
        .where(
            ManualAttendee.show_id == show_id,
            ManualAttendee.notification_confirmed_at.is_(None),
            ManualAttendee.organizer_reminded_at.is_(None),
        )
        .order_by(ManualAttendee.id)
        .limit(limit)
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


async def mark_manual_attendees_reminded(session: AsyncSession, attendee_ids: list[int]) -> None:
    if not attendee_ids:
        return
    await session.execute(
        update(ManualAttendee)
        .where(ManualAttendee.id.in_(attendee_ids))
        .values(organizer_reminded_at=_utcnow())
    )
    await session.commit()


async def confirm_manual_attendees_notified(session: AsyncSession, show_id: int) -> int:
    result = await session.execute(
        update(ManualAttendee)
        .where(
            ManualAttendee.show_id == show_id,
            ManualAttendee.notification_confirmed_at.is_(None),
        )
        .values(notification_confirmed_at=_utcnow())
    )
    await session.commit()
    return int(result.rowcount or 0)


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


async def claim_manual_announcement(session: AsyncSession, show_id: int) -> bool:
    """Reserve the first announcement while holding the show row lock.

    Both the bot and Mini App use this before a Telegram network call, preventing
    two near-simultaneous button presses from publishing the same show twice.
    """
    show = await session.scalar(select(Show).where(Show.id == show_id).with_for_update())
    if show is None or await has_any_announcement_been_sent(session, show_id):
        await session.rollback()
        return False
    session.add(AnnouncementLog(show_id=show_id, announcement_type="manual"))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False
    return True


async def claim_repeat_announcement(
    session: AsyncSession, show_id: int, idempotency_key: str,
) -> str | None:
    """Reserve one explicitly confirmed repeat using a stable request key."""
    digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]
    announcement_type = f"repeat_{digest}"
    session.add(AnnouncementLog(show_id=show_id, announcement_type=announcement_type))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return None
    return announcement_type


async def release_announcement_claim(
    session: AsyncSession, show_id: int, announcement_type: str,
) -> None:
    await session.execute(delete(AnnouncementLog).where(
        AnnouncementLog.show_id == show_id,
        AnnouncementLog.announcement_type == announcement_type,
        AnnouncementLog.channel_message_id.is_(None),
    ))
    await session.commit()


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
    session: AsyncSession, show_id: int, channel_message_id: int | None, ann_type: str = "manual"
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
    logger.info("created venue id=%s name=%s city=%s", venue.id, name, city)
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
    logger.info("created team id=%s name=%s creator_id=%s", team.id, name, creator_id)
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


# ── Free ad channels ────────────────────────────────────────────────────────

async def list_ad_channels(session: AsyncSession) -> list[FreeAdChannel]:
    result = await session.execute(select(FreeAdChannel).order_by(FreeAdChannel.username))
    return list(result.scalars().all())


async def get_active_ad_channels(session: AsyncSession) -> list[FreeAdChannel]:
    result = await session.execute(
        select(FreeAdChannel).where(FreeAdChannel.is_active == True).order_by(FreeAdChannel.username)
    )
    return list(result.scalars().all())


async def add_ad_channel(session: AsyncSession, username: str) -> FreeAdChannel | None:
    clean = "@" + username.lstrip("@").lower()
    existing = await session.execute(select(FreeAdChannel).where(FreeAdChannel.username == clean))
    if existing.scalar_one_or_none():
        return None
    ch = FreeAdChannel(username=clean)
    session.add(ch)
    await session.commit()
    await session.refresh(ch)
    return ch


async def toggle_ad_channel(session: AsyncSession, channel_id: int) -> FreeAdChannel | None:
    result = await session.execute(select(FreeAdChannel).where(FreeAdChannel.id == channel_id))
    ch = result.scalar_one_or_none()
    if ch is None:
        return None
    ch.is_active = not ch.is_active
    await session.commit()
    await session.refresh(ch)
    return ch


async def delete_ad_channel(session: AsyncSession, channel_id: int) -> bool:
    result = await session.execute(select(FreeAdChannel).where(FreeAdChannel.id == channel_id))
    ch = result.scalar_one_or_none()
    if ch is None:
        return False
    await session.delete(ch)
    await session.commit()
    return True
