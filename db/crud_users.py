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

from db.crud_access import IssuedInvite
from db.crud_access import _token_digest

__all__ = ['upsert_user', 'get_user_by_telegram_id', 'delete_or_anonymize_user_data', 'mark_onboarding_done', 'get_user_by_username', 'get_user_by_id', 'set_user_role', 'get_all_organizers', 'create_invite_token', 'consume_invite_token']


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


async def create_invite_token(session: AsyncSession, role: UserRole = UserRole.organizer) -> IssuedInvite:
    from config import settings
    raw_token = secrets.token_urlsafe(32)
    invite = InviteToken(
        token=_token_digest(raw_token),
        role=role,
        expires_at=_utcnow() + timedelta(hours=settings.INVITE_TTL_HOURS),
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)
    logger.info("created invite token id=%s role=%s", invite.id, invite.role)
    return IssuedInvite(invite.id, raw_token, role=invite.role, expires_at=invite.expires_at)


async def consume_invite_token(session: AsyncSession, token: str, user_id: int) -> InviteToken | None:
    result = await session.execute(
        select(InviteToken)
        .where(
            InviteToken.token == _token_digest(token),
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
