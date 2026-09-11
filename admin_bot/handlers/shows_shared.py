from __future__ import annotations

import io

import qrcode

from app_logging import get_project_logger
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, BufferedInputFile, LinkPreviewOptions, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from aiogram3_calendar import simple_cal_callback
from admin_bot.ru_calendar import RuCalendar
from datetime import date as _date
from config import ADMIN_ID_LIST, settings
from db.base import AsyncSessionLocal
from db import crud
from db.models import UserRole
from admin_bot.keyboards.reply import (
    main_menu_kb, promotion_context_kb, registrations_context_kb,
    shows_context_kb, show_context_kb, flow_context_kb, settings_context_kb,
    miniapp_launch_kb,
)
from admin_bot.telegram_usernames import normalize_telegram_username, normalize_telegram_username_list
from admin_bot.security import can_manage_owned, deny, is_admin, manageable_show
from html_utils import formatted_description, h
from time_utils import format_local, local_date, local_naive_to_utc, local_now
from telegram_delivery import send_with_retry
from scheduler.jobs import build_announcement_text, send_to_channel, cache_poster_for_public_bot, MAPS_RE, DATE_RE, TIME_RE, _location_line, _fmt_date, _registrar_line
from admin_bot.keyboards.inline import (
    shows_list_kb, shows_filter_kb, show_detail_kb, show_created_kb, edit_show_fields_kb,
    confirm_kb, confirm_with_back_kb, fsm_cancel_kb, fsm_skip_cancel_kb, venue_kb, city_kb,
    team_kb, team_select_kb, settings_kb, show_section_kb, edit_notification_mode_kb,
)
from admin_bot.callbacks import (
    AdminShowActionCb, AdminShowFieldCb, AdminFilterStatusCb,
    CityCb, VenueCb, TimePresetCb, TeamCb,
)

logger = get_project_logger(__name__)
MAX_POSTER_TEXT_LENGTH = 1800


class CreateShowFSM(StatesGroup):
    team_name = State()
    title = State()
    show_date = State()
    select_time = State()
    select_city = State()
    city = State()
    select_venue = State()
    location = State()
    location_url = State()
    max_seats = State()
    poster_text = State()
    poster_image = State()
    registrar = State()
    confirm = State()



_TOTAL_STEPS_PRESET = 8   # venue preset: includes optional registrar step
_TOTAL_STEPS_CUSTOM = 10   # custom venue: includes optional registrar step


def _progress(step: int, total: int = _TOTAL_STEPS_PRESET) -> str:
    bar = "●" * step + "○" * (total - step)
    return f"<code>{bar}</code>  {step}/{total}\n"


class EditShowFSM(StatesGroup):
    field = State()
    new_value = State()
    show_date = State()
    select_time = State()


class CloneShowFSM(StatesGroup):
    show_date = State()
    select_time = State()


def _registrar_name(registrar, username: str | None = None) -> str | None:
    if registrar:
        return registrar.first_name or (f"@{registrar.username}" if registrar.username else f"id{registrar.telegram_id}")
    return f"@{username}" if username else None


def _registrar_link(username: str | None, label: str | None = None) -> str | None:
    if not username:
        return h(label) if label else None
    username = username.lstrip("@")
    return f'<a href="https://t.me/{username}">{h(label or ("@" + username))}</a>'


def _show_summary(data: dict) -> str:
    location_str = data.get('location', '')
    if data.get('location_url'):
        location_str += f"\n     🗺 {data['location_url']}"
    return (
        f"📋 <b>Проверьте данные шоу:</b>\n\n"
        f"🎭 Название: {h(data.get('title', ''))}\n"
        f"👥 Команда: {h(data.get('team_name', ''))}\n"
        f"📅 Дата: {data.get('show_date_str')}\n"
        f"🏙 Город: {h(data.get('city', ''))}\n"
        f"📍 Площадка: {h(location_str)}\n"
        f"🪑 Мест: {data.get('max_seats')}\n"
        f"📝 Текст афиши: {h(data.get('poster_text') or '(не указан)')}\n"
        f"🖼 Изображение: {'есть' if data.get('poster_file_id') else 'нет'}\n"
        f"👥 Ответственный за записи: "
        f"{_registrar_link(data.get('registrar_username'), data.get('registrar_name')) or '(через бот)'}"
    )


def _validate_poster_text(text: str) -> str | None:
    if len(text) > MAX_POSTER_TEXT_LENGTH:
        return f"❌ Текст афиши слишком длинный. Максимум — {MAX_POSTER_TEXT_LENGTH} символов. Сократи и попробуй ещё раз:"
    if DATE_RE.search(text):
        return "❌ Текст афиши не должен содержать дату — она уже есть в отдельном поле. Убери дату и попробуй ещё раз:"
    if TIME_RE.search(text):
        return "❌ Текст афиши не должен содержать время — оно уже есть в отдельном поле. Убери время и попробуй ещё раз:"
    if MAPS_RE.search(text):
        return "❌ Текст афиши не должен содержать ссылку на Google Maps — она уже есть в поле «Площадка». Убери ссылку и попробуй ещё раз:"
    return None


def _is_google_maps_url(url: str) -> bool:
    return any(url.startswith(prefix) for prefix in (
        "https://maps.google", "https://www.google.com/maps",
        "https://goo.gl/maps", "https://maps.app.goo.gl",
        "http://maps.google", "http://www.google.com/maps",
    ))


# ── Create flow ─────────────────────────────────────────────────────────────

__all__ = [name for name in globals() if not name.startswith("__")]
