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

from db.crud_registrations import count_active_registrations
from db.crud_registrations import get_registration

__all__ = ['change_checkin_counter', 'claim_checkin_milestones', 'release_checkin_milestones', 'get_feedback_candidates', 'mark_feedback_requested', 'can_submit_feedback', 'save_feedback', 'get_show_feedback', 'set_reminder_pref', 'get_registered_users_for_show', 'add_manual_attendees', 'get_manual_attendees', 'get_pending_manual_attendees_for_reminder']


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


async def add_manual_attendees(
    session: AsyncSession,
    show_id: int,
    names: list[str],
    source: str | None = "manual",
    contacts: list[str | None] | None = None,
    guests: list[int] | None = None,
) -> int:
    show_result = await session.execute(
        select(Show).where(Show.id == show_id).with_for_update()
    )
    show = show_result.scalar_one_or_none()
    if show is None or not show.is_active or show.show_date < _utcnow() or (show.registration_closes_at and show.registration_closes_at <= _utcnow()):
        return 0
    occupied = await count_active_registrations(session, show_id)
    normalized_guests = guests or [0] * len(names)
    if any(guest_count < 0 or guest_count > show.max_guests for guest_count in normalized_guests):
        return 0
    if occupied + sum(guest_count + 1 for guest_count in normalized_guests) > show.max_seats:
        return 0
    normalized_contacts = contacts or [None] * len(names)
    for name, contact, guest_count in zip(names, normalized_contacts, normalized_guests):
        session.add(ManualAttendee(
            show_id=show_id,
            name=name.strip(),
            contact=contact.strip() if contact and contact.strip() else None,
            guests=guest_count,
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
