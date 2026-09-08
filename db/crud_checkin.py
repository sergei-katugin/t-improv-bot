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

from db.crud_registrations import get_registration

__all__ = ['mark_reminded', 'mark_reminded_many', 'set_confirmed', 'toggle_registration_checkin', 'toggle_manual_attendee_checkin', 'set_registration_checkin_count', 'set_manual_checkin_count']


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
