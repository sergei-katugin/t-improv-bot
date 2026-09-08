from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from sqlalchemy import select, func, exists, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Show, Registration, WaitlistEntry, ShowFeedback, AnnouncementLog, InviteToken, ManualAttendee, UserRole, Venue, Team, FreeAdChannel, ConnectedRegistrationChat, ShowCheckinStaff, CheckinInviteToken, _utcnow
from app_logging import get_project_logger

logger = get_project_logger(__name__)

from db.crud_shows import get_show_with_dependents

__all__ = ['deactivate_show', 'delete_show', 'count_active_registrations', 'get_registration', 'register_user_safe', 'update_registration_guests_safe', 'cancel_registration', 'join_waitlist', 'promote_waitlist', 'get_user_registrations', 'get_show_registrations', 'get_registrations_for_reminder']


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
        select(func.coalesce(func.sum(ManualAttendee.guests + 1), 0)).where(ManualAttendee.show_id == show_id)
    )
    return int(registered_result.scalar_one()) + int(manual_result.scalar_one())


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
    if guests < 0 or guests > 6 or not 2 <= len(attendee_name.strip()) <= 100:
        return None
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow() or (show.registration_closes_at and show.registration_closes_at <= _utcnow()):
        return None
    if guests > show.max_guests:
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
    if guests < 0 or guests > 6:
        return None
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow() or (show.registration_closes_at and show.registration_closes_at <= _utcnow()):
        return None
    if guests > show.max_guests:
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


async def join_waitlist(session: AsyncSession, show_id: int, user_id: int, attendee_name: str) -> tuple[WaitlistEntry | None, int]:
    show = await session.get(Show, show_id)
    if show is None or not show.is_active or show.show_date <= _utcnow() or (show.registration_closes_at and show.registration_closes_at <= _utcnow()):
        return None, 0
    active = await get_registration(session, show_id, user_id)
    if active and not active.is_cancelled:
        return None, 0
    if await count_active_registrations(session, show_id) < show.max_seats:
        return None, 0
    existing = await session.scalar(select(WaitlistEntry).where(WaitlistEntry.show_id == show_id, WaitlistEntry.user_id == user_id))
    if existing:
        if existing.promoted_at is None and existing.cancelled_at is None:
            position = int(await session.scalar(select(func.count(WaitlistEntry.id)).where(WaitlistEntry.show_id == show_id, WaitlistEntry.promoted_at.is_(None), WaitlistEntry.cancelled_at.is_(None), WaitlistEntry.created_at <= existing.created_at)) or 0)
            return existing, position
        existing.promoted_at = None
        existing.cancelled_at = None
        existing.created_at = _utcnow()
        existing.attendee_name = attendee_name.strip()
        entry = existing
    else:
        entry = WaitlistEntry(show_id=show_id, user_id=user_id, attendee_name=attendee_name.strip(), guests=0)
        session.add(entry)
    await session.commit()
    position = int(await session.scalar(select(func.count(WaitlistEntry.id)).where(WaitlistEntry.show_id == show_id, WaitlistEntry.promoted_at.is_(None), WaitlistEntry.cancelled_at.is_(None))) or 0)
    return entry, position


async def promote_waitlist(session: AsyncSession, show_id: int) -> tuple[Registration, User] | None:
    show = await session.scalar(select(Show).where(Show.id == show_id).with_for_update())
    if show is None or not show.is_active or show.show_date <= _utcnow() or (show.registration_closes_at and show.registration_closes_at <= _utcnow()):
        return None
    occupied = await count_active_registrations(session, show_id)
    if occupied >= show.max_seats:
        return None
    entry = await session.scalar(select(WaitlistEntry).options(selectinload(WaitlistEntry.user)).where(
        WaitlistEntry.show_id == show_id, WaitlistEntry.promoted_at.is_(None), WaitlistEntry.cancelled_at.is_(None),
    ).order_by(WaitlistEntry.created_at, WaitlistEntry.id).with_for_update().limit(1))
    if entry is None or occupied + 1 + entry.guests > show.max_seats:
        return None
    registration = await get_registration(session, show_id, entry.user_id)
    if registration is None:
        registration = Registration(show_id=show_id, user_id=entry.user_id, attendee_name=entry.attendee_name, guests=entry.guests)
        session.add(registration)
    else:
        registration.attendee_name = entry.attendee_name
        registration.guests = entry.guests
        registration.is_cancelled = False
        registration.cancelled_at = None
        registration.registered_at = _utcnow()
        registration.confirmed = None
    entry.promoted_at = _utcnow()
    await session.commit()
    await session.refresh(registration)
    return registration, entry.user


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
