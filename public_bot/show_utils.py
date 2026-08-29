from __future__ import annotations

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import show_detail_kb
from scheduler.jobs import _registrar_line
from html_utils import h
from time_utils import format_local


def show_text(show, seats_left: int, reg=None) -> str:
    lines = [
        f"🎭 <b>{h(show.title)}</b>",
        f"👥 Команда: {h(show.team_name)}",
        f"📅 {format_local(show.show_date)}",
        f"🏙 {h(show.city)}  |  📍 {h(show.location)}",
        f"🪑 Свободных мест: {seats_left}/{show.max_seats}",
    ]
    registrar_line = _registrar_line(show)
    if registrar_line:
        lines.append(registrar_line)
    if reg and not reg.is_cancelled:
        guests = reg.guests or 0
        total = 1 + guests
        suffix = f" +{guests}" if guests > 0 else ""
        lines.append(f"✅ Ты записан(а): {total} чел.{suffix}")
    if show.poster_text:
        lines.append("")
        lines.append(h(show.poster_text))
    return "\n".join(lines)


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
    await target.answer(text, reply_markup=kb)
