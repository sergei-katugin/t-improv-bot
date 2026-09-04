from __future__ import annotations

from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import UserRole


def is_admin(db_user, is_super_admin: bool = False) -> bool:
    return bool(
        is_super_admin
        or (db_user is not None and db_user.role == UserRole.admin)
    )


def can_manage_owned(creator_id: int | None, db_user, is_super_admin: bool = False) -> bool:
    return is_admin(db_user, is_super_admin) or bool(
        db_user is not None and creator_id is not None and db_user.id == creator_id
    )


async def manageable_show(
    session: AsyncSession, show_id: int, db_user, is_super_admin: bool = False,
):
    show = await crud.get_show(session, show_id)
    if show is None or not can_manage_owned(show.creator_id, db_user, is_super_admin):
        return None
    return show


async def checkin_accessible_show(
    session: AsyncSession, show_id: int, db_user, is_super_admin: bool = False,
):
    show = await crud.get_show(session, show_id)
    if show is None:
        return None
    if can_manage_owned(show.creator_id, db_user, is_super_admin):
        return show
    if db_user is not None and await crud.has_checkin_access(session, show_id, db_user.id):
        return show
    return None


async def deny(event: CallbackQuery | Message, text: str = "⛔ Недостаточно прав.") -> None:
    if isinstance(event, CallbackQuery):
        await event.answer(text, show_alert=True)
    else:
        await event.answer(text)
