from __future__ import annotations

from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import show_detail_kb
from scheduler.jobs import build_announcement_text


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def show_text(show, seats_left: int, reg=None) -> str:
    attendee_line = None
    if reg and not reg.is_cancelled:
        guests = reg.guests or 0
        total = 1 + guests
        suffix = f" +{guests}" if guests > 0 else ""
        attendee_line = f"✅ Ты записан(а): {total} чел.{suffix}"
    return build_announcement_text(
        show,
        seats_left=seats_left,
        attendee_line=attendee_line,
        include_registration=False,
    )


async def render_show_detail(target: Message, show_id: int, db_user: User, session: AsyncSession) -> None:
    show = await crud.get_show(session, show_id)
    if show is None:
        await target.answer("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)

    seats_left = max(0, show.max_seats - active_count)
    is_registered = reg is not None and not reg.is_cancelled
    text = show_text(show, seats_left, reg=reg)
    kb = show_detail_kb(show_id, is_registered, seats_left)
    await target.answer(text, reply_markup=kb, link_preview_options=NO_LINK_PREVIEW)
