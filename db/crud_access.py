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

__all__ = ['IssuedInvite', '_token_digest', 'remember_registration_chat', 'get_registration_chats', 'create_checkin_invite', 'consume_checkin_invite', 'has_any_checkin_access', 'has_checkin_access']


@dataclass(frozen=True)
class IssuedInvite:
    id: int
    token: str
    role: UserRole | None = None
    expires_at: datetime | None = None


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


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


async def create_checkin_invite(session: AsyncSession, show_id: int, ttl_hours: int = 24) -> IssuedInvite:
    raw_token = secrets.token_urlsafe(24)
    invite = CheckinInviteToken(
        token=_token_digest(raw_token),
        show_id=show_id,
        expires_at=_utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    return IssuedInvite(invite.id, raw_token, expires_at=invite.expires_at)


async def consume_checkin_invite(session: AsyncSession, token: str, user_id: int) -> int | None:
    result = await session.execute(
        select(CheckinInviteToken)
        .where(
            CheckinInviteToken.token == _token_digest(token),
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
