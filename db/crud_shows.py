from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from sqlalchemy import case, select, func, exists, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import User, Show, Registration, WaitlistEntry, ShowFeedback, AnnouncementLog, InviteToken, ManualAttendee, UserRole, Venue, Team, FreeAdChannel, ConnectedRegistrationChat, ShowCheckinStaff, CheckinInviteToken, _utcnow
from app_logging import get_project_logger

logger = get_project_logger(__name__)

__all__ = ['create_show', 'get_show', 'get_show_with_dependents', 'list_upcoming_shows', 'has_upcoming_shows', 'has_user_registrations', 'get_menu_flags', 'list_all_shows', 'list_shows_by_creator', 'list_finished_shows_with_registration_chat', 'mark_registration_chat_summary_sent', 'get_show_outcome', 'get_show_outcomes', 'clear_registration_chat_if_matches', 'update_show']

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
    title_newcomer: str | None = None,
    poster_text_newcomer: str | None = None,
    max_guests: int = 6,
    registration_closes_at: datetime | None = None,
    registrar_id: int | None = None,
    registrar_username: str | None = None,
    checkin_enabled: bool = False, checkin_mode: str = "named", checkin_report_every: int = 10,
    feedback_enabled: bool = True,
) -> Show:
    show = Show(
        title=title,
        title_newcomer=title_newcomer,
        team_name=team_name,
        show_date=show_date,
        location=location,
        location_url=location_url,
        city=city,
        poster_text=poster_text,
        poster_text_newcomer=poster_text_newcomer,
        poster_file_id=poster_file_id,
        max_seats=max_seats,
        max_guests=max_guests,
        registration_closes_at=show_date - timedelta(minutes=5),
        creator_id=creator_id,
        registrar_id=registrar_id,
        registrar_username=registrar_username,
        checkin_enabled=checkin_enabled, checkin_mode=checkin_mode, checkin_report_every=checkin_report_every,
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
    limit: int | None = None,
    offset: int = 0,
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
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
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


async def list_finished_shows_with_registration_chat(session: AsyncSession) -> list[Show]:
    result = await session.execute(
        select(Show)
        .where(
            Show.registration_chat_id.is_not(None),
            Show.registration_chat_summary_sent_at.is_(None),
            Show.show_date <= _utcnow() - timedelta(hours=24),
        )
        .order_by(Show.id)
        .limit(100)
    )
    return list(result.scalars().all())


async def mark_registration_chat_summary_sent(session: AsyncSession, show_id: int, chat_id: int) -> bool:
    result = await session.execute(
        update(Show)
        .where(Show.id == show_id, Show.registration_chat_id == chat_id, Show.registration_chat_summary_sent_at.is_(None))
        .values(registration_chat_summary_sent_at=_utcnow(), updated_at=_utcnow())
    )
    await session.commit()
    return bool(result.rowcount)


async def get_show_outcome(session: AsyncSession, show_id: int) -> dict[str, int | float]:
    return (await get_show_outcomes(session, [show_id]))[show_id]


async def get_show_outcomes(
    session: AsyncSession, show_ids: list[int],
) -> dict[int, dict[str, int | float]]:
    """Return reporting totals in three grouped queries, independent of show count."""
    outcomes = {
        show_id: {
            "registered": 0, "cancelled": 0, "arrived": 0,
            "feedback_count": 0, "average_rating": 0.0,
        }
        for show_id in show_ids
    }
    if not outcomes:
        return outcomes

    registration_rows = (await session.execute(
        select(
            Registration.show_id,
            func.coalesce(func.sum(case((Registration.is_cancelled == False, Registration.guests + 1), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == True, 1), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == False, Registration.checked_in_count), else_=0)), 0),
        )
        .where(Registration.show_id.in_(outcomes))
        .group_by(Registration.show_id)
    )).all()
    manual_rows = (await session.execute(
        select(
            ManualAttendee.show_id,
            func.coalesce(func.sum(ManualAttendee.guests + 1), 0),
            func.coalesce(func.sum(ManualAttendee.checked_in_count), 0),
        )
        .where(ManualAttendee.show_id.in_(outcomes))
        .group_by(ManualAttendee.show_id)
    )).all()
    feedback_rows = (await session.execute(
        select(
            ShowFeedback.show_id, func.count(ShowFeedback.id),
            func.coalesce(func.avg(ShowFeedback.rating), 0),
        )
        .where(ShowFeedback.show_id.in_(outcomes))
        .group_by(ShowFeedback.show_id)
    )).all()

    for show_id, registered, cancelled, arrived in registration_rows:
        outcomes[show_id].update(
            registered=int(registered), cancelled=int(cancelled), arrived=int(arrived),
        )
    for show_id, registered, arrived in manual_rows:
        outcomes[show_id]["registered"] += int(registered)
        outcomes[show_id]["arrived"] += int(arrived)
    for show_id, count, average in feedback_rows:
        outcomes[show_id].update(feedback_count=int(count), average_rating=float(average))
    return outcomes

async def clear_registration_chat_if_matches(session: AsyncSession, show_id: int, chat_id: int) -> bool:
    result = await session.execute(
        update(Show)
        .where(Show.id == show_id, Show.registration_chat_id == chat_id)
        .values(registration_chat_id=None, registration_chat_title=None, updated_at=_utcnow())
    )
    await session.commit()
    return bool(result.rowcount)

async def update_show(session: AsyncSession, show_id: int, **fields) -> Show | None:
    show = await get_show(session, show_id)
    if show is None:
        return None
    if "show_date" in fields:
        fields["registration_closes_at"] = fields["show_date"] - timedelta(minutes=5)
    for key, value in fields.items():
        setattr(show, key, value)
    show.updated_at = _utcnow()
    await session.commit()
    await session.refresh(show)
    logger.info("updated show id=%s fields=%s", show_id, list(fields.keys()))
    return show
