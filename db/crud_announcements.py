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

__all__ = ['delete_manual_attendee', 'mark_manual_attendees_reminded', 'confirm_manual_attendees_notified', 'has_announcement_been_sent', 'has_any_announcement_been_sent', 'claim_manual_announcement', 'claim_repeat_announcement', 'release_announcement_claim']


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
