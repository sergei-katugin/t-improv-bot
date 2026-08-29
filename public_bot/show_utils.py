from __future__ import annotations

from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import registrar_username, show_detail_kb
from scheduler.jobs import build_announcement_text
from html_utils import h


NO_LINK_PREVIEW = LinkPreviewOptions(is_disabled=True)


def show_text(show, seats_left: int, reg=None) -> str:
    attendee_line = None
    if reg and not reg.is_cancelled:
        guests = reg.guests or 0
        total = 1 + guests
        suffix = f" +{guests}" if guests > 0 else ""
        attendee_line = f"✅ Ты записан(а): {total} чел.{suffix}"
    text = build_announcement_text(
        show,
        seats_left=seats_left,
        attendee_line=attendee_line,
        include_registration=False,
    )
    username = registrar_username(show)
    if username:
        text += f'\n\n❓ По вопросам записи можно написать <a href="https://t.me/{h(username)}">@{h(username)}</a>.'
    return text


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
    kb = show_detail_kb(show, is_registered, seats_left)
    await target.answer(text, reply_markup=kb, link_preview_options=NO_LINK_PREVIEW)
