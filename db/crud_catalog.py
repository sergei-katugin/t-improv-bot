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

__all__ = ['mark_announcement_sent', 'save_channel_message_id', 'get_last_channel_message_id', 'list_venues', 'get_venue', 'create_venue', 'update_venue', 'delete_venue', 'seed_venues', 'list_teams', 'get_team', 'create_team', 'update_team', 'delete_team', 'list_ad_channels', 'get_active_ad_channels', 'add_ad_channel', 'toggle_ad_channel', 'delete_ad_channel']


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
