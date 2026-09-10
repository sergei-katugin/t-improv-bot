from __future__ import annotations

import re
from datetime import datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import settings
from html_utils import h
from time_utils import format_local, utc_to_local

MAPS_RE = re.compile(r'(maps\.google|goo\.gl/maps|maps\.app\.goo\.gl|google\.com/maps)', re.I)
DATE_RE = re.compile(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}')
TIME_RE = re.compile(r'\b\d{1,2}:\d{2}\b')


def _register_button(show) -> InlineKeyboardMarkup | None:
    if show is None or not show.id:
        return None
    url = f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show.id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Записаться на шоу", url=url)
    ]])


_MONTHS_GEN = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _fmt_date(dt) -> str:
    dt = utc_to_local(dt)
    return f"{dt.day} {_MONTHS_GEN[dt.month]}, {_WEEKDAYS_RU[dt.weekday()]}, {dt.strftime('%H:%M')}"


def _location_line(show, plain: bool = False) -> str:
    if show.location_url and not plain:
        return f'📍 <a href="{h(show.location_url)}">{h(show.location)}</a>, {h(show.city)}'
    return f"📍 {h(show.location)}, {h(show.city)}"


def _registrar_line(show) -> str | None:
    bot_username = settings.PUBLIC_BOT_USERNAME.lstrip("@")
    bot_link = f'<a href="https://t.me/{bot_username}">@{h(bot_username)}</a>'
    registrar = getattr(show, "registrar", None)
    username = getattr(show, "registrar_username", None) or (registrar.username if registrar else None)
    if username:
        username = username.lstrip("@")
        person_link = f'<a href="https://t.me/{username}">@{h(username)}</a>'
        return f"👥 Записаться тут: <b>через бота</b> {bot_link} или у {person_link}"
    return f"👥 Записаться тут: <b>через бота</b> {bot_link}"


_ANN_HEADERS = {
    "7d": "🎭 Через неделю:",
    "2d": "🎭 Через два дня:",
    "1d": "🎭 Завтра:",
    "0d": "🎭 Сегодня!",
}

_REGISTER_NOTE = "👆 Нажми кнопку — и твоё место сразу запомнится!"


def build_announcement_text(
    show,
    ann_type: str | None = None,
    *,
    seats_left: int | None = None,
    attendee_line: str | None = None,
    include_registration: bool = True,
) -> str:
    if ann_type is None:
        header = f"🎭 <b>{h(show.title)}</b>"
    else:
        prefix = _ANN_HEADERS.get(ann_type, "🎭")
        header = f"{prefix} <b>{h(show.title)}</b>"

    poster = show.poster_text or ""
    poster_has_date = bool(DATE_RE.search(poster))
    poster_has_maps = bool(MAPS_RE.search(poster))

    lines = [header]
    if getattr(show, "team_name", None):
        lines.append(f"👥 Команда: {h(show.team_name)}")
    if not poster_has_date:
        lines.append(f"📅 {_fmt_date(show.show_date)}")
    lines.append(_location_line(show, plain=poster_has_maps))
    if seats_left is not None:
        lines.append(f"🪑 Свободных мест: {seats_left}/{show.max_seats}")
    if include_registration:
        registrar_line = _registrar_line(show)
        if registrar_line:
            lines.append(registrar_line)
    if attendee_line:
        lines.append(attendee_line)

    if poster:
        lines.append("")
        lines.append(h(poster))

    if ann_type is not None:
        lines.append("")
        lines.append(_REGISTER_NOTE)

    return "\n".join(lines)


def build_personal_reminder(
    show, custom_intro: str | None = None
) -> tuple[str, InlineKeyboardMarkup | None]:
    intro = custom_intro or "👋 Напоминание! Завтра шоу, на которое ты записан(а):"
    lines = [intro, "", build_announcement_text(show)]
    text = "\n".join(lines)
    kb = _register_button(show)
    return text, kb
