from __future__ import annotations

import io
import qrcode

from app_logging import get_project_logger
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.filters import Command
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
from admin_bot.keyboards.reply import main_menu_kb
from scheduler.jobs import build_announcement_text, send_to_channel, cache_poster_for_public_bot, MAPS_RE, DATE_RE, TIME_RE, _location_line, _fmt_date
from admin_bot.keyboards.inline import (
    shows_list_kb, shows_filter_kb, show_detail_kb, show_created_kb, edit_show_fields_kb,
    confirm_kb, confirm_with_back_kb, fsm_cancel_kb, fsm_skip_cancel_kb, venue_kb, city_kb,
    team_kb, team_select_kb, settings_kb,
)
from admin_bot.callbacks import (
    AdminShowActionCb, AdminShowFieldCb, AdminFilterStatusCb,
    CityCb, VenueCb, TimePresetCb, TeamCb,
)

logger = get_project_logger(__name__)
router = Router()


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


def _show_summary(data: dict) -> str:
    location_str = data.get('location', '')
    if data.get('location_url'):
        location_str += f"\n     🗺 {data['location_url']}"
    return (
        f"📋 <b>Проверьте данные шоу:</b>\n\n"
        f"🎭 Название: {data.get('title')}\n"
        f"👥 Команда: {data.get('team_name')}\n"
        f"📅 Дата: {data.get('show_date_str')}\n"
        f"🏙 Город: {data.get('city')}\n"
        f"📍 Площадка: {location_str}\n"
        f"🪑 Мест: {data.get('max_seats')}\n"
        f"📝 Текст афиши: {data.get('poster_text') or '(не указан)'}\n"
        f"🖼 Изображение: {'есть' if data.get('poster_file_id') else 'нет'}\n"
        f"👥 Ответственный за записи: {data.get('registrar_name') or '(через бот)'}"
    )


def _validate_poster_text(text: str) -> str | None:
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

@router.message(Command("start"))
async def cmd_start(message: Message, session: AsyncSession, is_super_admin: bool = False):
    from admin_bot.handlers.onboarding import start_onboarding
    user = await crud.upsert_user(
        session, message.from_user.id, message.from_user.username,
        message.from_user.first_name, message.from_user.last_name,
    )
    if not user.onboarding_done:
        await start_onboarding(message)
        return
    await message.answer("👋 Привет!", reply_markup=main_menu_kb())


@router.message(Command("home"))
async def cmd_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=main_menu_kb())


@router.message(Command("create_show"))
@router.message(F.text == "🆕 Создать")
@router.callback_query(F.data == "admin_create_show")
async def cmd_create_show(event, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.clear()
    await state.set_state(CreateShowFSM.team_name)
    await msg.answer(
        "🎭 <b>Создание нового шоу</b>\n\n"
        "Я задам несколько вопросов — это займёт около минуты.\n"
        "Понадобится:\n"
        "• команда и название шоу\n"
        "• дата и время\n"
        "• площадка — если выбрать из списка, город и количество мест подставятся автоматически\n"
        "• текст и изображение для афиши (можно пропустить)\n\n"
        "💡 Шоу не будет опубликовано автоматически — анонс отправляется вручную, когда ты будешь готов.\n\n"
        "На любом шаге можно нажать ◀️ Назад или ❌ Отмена.",
    )
    await msg.answer(
        f"{_progress(1)}Выбери команду из списка или введи своё название:",
        reply_markup=team_kb(),
    )


@router.message(F.text == "📋 Афиша")
@router.message(Command("shows"))
async def cmd_shows_message(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.clear()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(message, state, session, edit=False, can_manage=_can_manage(is_super_admin, db_user))


@router.message(F.text == "🎭 Моё")
@router.message(Command("my"))
@router.callback_query(F.data == "admin_my_shows")
async def cmd_my_shows(event, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    tg_id = event.from_user.id
    from admin_bot.handlers.registrations import _can_manage
    can_manage = _can_manage(is_super_admin, db_user)

    shows = await crud.list_shows_by_creator(session, tg_id)

    if not shows:
        text = "У тебя пока нет созданных шоу."
    else:
        text = f"🎭 <b>Мои шоу</b> ({len(shows)}):"

    kb = shows_list_kb(shows, can_manage=can_manage)
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=kb)
    else:
        await msg.edit_text(text, reply_markup=kb)


@router.message(F.text == "⚙️ Настройки")
@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext, db_user=None, is_super_admin: bool = False):
    await state.clear()
    is_admin = is_super_admin or (db_user is not None and db_user.role == UserRole.admin)
    await message.answer("⚙️ <b>Настройки</b>", reply_markup=settings_kb(is_admin=is_admin))


@router.callback_query(CreateShowFSM.team_name, F.data == "team_show_existing")
async def team_show_existing(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    teams = await crud.list_teams(session)
    if not teams:
        await callback.answer("Нет сохранённых команд. Создай новую или введи вручную.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{_progress(1)}Выбери команду из списка:",
        reply_markup=team_select_kb(teams),
    )


@router.callback_query(CreateShowFSM.team_name, F.data == "team_back_to_entry")
async def team_back_to_entry(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"{_progress(1)}Выбери команду из списка или введи своё название:",
        reply_markup=team_kb(),
    )


@router.callback_query(CreateShowFSM.team_name, TeamCb.filter())
async def process_team_select(callback: CallbackQuery, callback_data: TeamCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    if callback_data.team_id == 0:
        # "Другая" — manual text input
        await callback.message.edit_text(
            f"{_progress(1)}Введи название команды:",
            reply_markup=fsm_cancel_kb(),
        )
        await state.update_data(_team_manual=True)
        return
    team = await crud.get_team(session, callback_data.team_id)
    if team is None:
        await callback.message.answer("Команда не найдена. Попробуй ещё раз.")
        return
    await state.update_data(team_name=team.name, _team_manual=False)
    await callback.message.edit_text(f"✅ Команда: {team.name}")
    await callback.message.answer(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())
    await state.set_state(CreateShowFSM.title)


@router.message(CreateShowFSM.team_name, F.text)
async def process_team_name_manual(message: Message, state: FSMContext, session: AsyncSession):
    """Manual text input for 'Другая' team."""
    data = await state.get_data()
    if not data.get("_team_manual"):
        # Guard: if user typed without clicking "Другая", show the keyboard
        teams = await crud.list_teams(session)
        await message.answer(f"{_progress(1)}Выбери команду:", reply_markup=team_select_kb(teams))
        return
    if len(message.text.strip()) < 2:
        await message.answer("Название команды слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(team_name=message.text.strip(), _team_manual=False)
    await state.set_state(CreateShowFSM.title)
    await message.answer(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.title, F.text)
async def process_title(message: Message, state: FSMContext, session: AsyncSession):
    if len(message.text.strip()) < 2:
        await message.answer("Название шоу слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateShowFSM.show_date)
    now = datetime.utcnow()
    await message.answer(
        f"{_progress(3)}Выбери дату шоу:",
        reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
    )


@router.message(CreateShowFSM.show_date)
async def show_date_text_guard(message: Message, state: FSMContext, session: AsyncSession):
    now = datetime.utcnow()
    await message.answer(
        "👆 Выбери дату кнопками выше.",
        reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
    )


@router.callback_query(CreateShowFSM.show_date, simple_cal_callback.filter())
async def process_calendar(callback: CallbackQuery, callback_data: dict, state: FSMContext, session: AsyncSession):
    selected, date = await (await _make_calendar(session)).process_selection(callback, callback_data)
    if not selected:
        return
    if date.date() < datetime.utcnow().date():
        await callback.answer("❌ Дата в прошлом, выбери другую.", show_alert=True)
        return
    await state.update_data(picked_date=date.strftime("%d.%m.%Y"))
    await state.set_state(CreateShowFSM.select_time)
    await callback.message.answer(
        f"✅ Дата: {date.strftime('%d.%m.%Y')}\n\n"
        f"{_progress(3)}Выбери время начала:",
        reply_markup=_time_kb(),
    )


def _time_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    slots = ["17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
    builder = IKB()
    for t in slots:
        builder.button(text=t, callback_data=TimePresetCb(time=t).pack())
    builder.button(text="✏️ Другое", callback_data="time_custom")
    builder.button(text="◀️ Назад",  callback_data="fsm_back")
    builder.button(text="❌ Отмена", callback_data="fsm_cancel")
    builder.adjust(4, 3, 2)
    return builder.as_markup()


@router.callback_query(CreateShowFSM.select_time, TimePresetCb.filter())
async def process_time_preset(callback: CallbackQuery, callback_data: TimePresetCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    await _save_time(callback_data.time, callback.message, state, session, edit=True)


@router.callback_query(CreateShowFSM.select_time, F.data == "time_custom")
async def process_time_custom(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"{_progress(3)}Введи время начала (ЧЧ:ММ), например 19:00:",
        reply_markup=fsm_cancel_kb(),
    )


@router.message(CreateShowFSM.select_time, F.text)
async def process_time(message: Message, state: FSMContext, session: AsyncSession):
    raw = message.text.strip()
    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат. Введи время как ЧЧ:ММ, например 19:00:", reply_markup=fsm_cancel_kb())
        return
    await _save_time(raw, message, state, session, edit=False)


async def _save_time(raw: str, msg, state: FSMContext, session: AsyncSession, edit: bool):
    data = await state.get_data()
    dt = datetime.strptime(f"{data['picked_date']} {raw}", "%d.%m.%Y %H:%M")
    if dt <= datetime.utcnow():
        text = "❌ Дата и время уже в прошлом. Выбери другое время:"
        if edit:
            await msg.edit_text(text, reply_markup=_time_kb())
        else:
            await msg.answer(text, reply_markup=_time_kb())
        return
    await state.update_data(show_date=dt, show_date_str=f"{data['picked_date']} {raw}")
    await state.set_state(CreateShowFSM.select_venue)
    venues = await crud.list_venues(session)
    confirm_text = f"✅ Время: {raw}"
    if edit:
        await msg.edit_text(confirm_text)
    else:
        await msg.answer(confirm_text)
    await msg.answer(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))


@router.callback_query(CreateShowFSM.select_venue, VenueCb.filter())
async def process_venue_select(callback: CallbackQuery, callback_data: VenueCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    if callback_data.venue_id == 0:
        await state.update_data(_total=_TOTAL_STEPS_CUSTOM)
        await state.set_state(CreateShowFSM.location)
        await callback.message.edit_text(f"{_progress(4, _TOTAL_STEPS_CUSTOM)}Введи название площадки/театра:", reply_markup=fsm_cancel_kb())
    else:
        venue = await crud.get_venue(session, callback_data.venue_id)
        if venue is None:
            await callback.message.answer("Площадка не найдена. Попробуй ещё раз.")
            return
        await state.update_data(
            location=venue.name, location_url=venue.maps_url,
            city=venue.city, max_seats=venue.default_seats,
            _total=_TOTAL_STEPS_PRESET,
        )
        await state.set_state(CreateShowFSM.poster_text)
        await callback.message.edit_text(
            f"✅ Площадка: {venue.name} ({venue.city}) · {venue.default_seats} мест"
        )
        await callback.message.answer(
            f"{_progress(5, _TOTAL_STEPS_PRESET)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
        )


@router.message(CreateShowFSM.location, F.text)
async def process_location(message: Message, state: FSMContext):
    await state.update_data(location=message.text.strip())
    await state.set_state(CreateShowFSM.location_url)
    await message.answer(
        f"{_progress(5, _TOTAL_STEPS_CUSTOM)}Введи ссылку на Google Maps для этой площадки:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
    )


@router.callback_query(CreateShowFSM.location_url, F.data == "fsm_skip_location_url")
async def skip_location_url(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(location_url=None)
    await state.set_state(CreateShowFSM.select_city)
    await callback.message.edit_text("⏭ Ссылка на карты пропущена.")
    await callback.message.answer(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:", reply_markup=city_kb())


@router.message(CreateShowFSM.location_url, F.text)
async def process_location_url(message: Message, state: FSMContext):
    url = message.text.strip()
    if not _is_google_maps_url(url):
        await message.answer(
            "Это не ссылка на Google Maps. Примеры допустимых ссылок:\n"
            "• https://maps.google.com/...\n"
            "• https://goo.gl/maps/...\n"
            "• https://maps.app.goo.gl/...\n\n"
            "Попробуй ещё раз или нажми ⏭ Пропустить:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
        )
        return
    await state.update_data(location_url=url)
    await state.set_state(CreateShowFSM.select_city)
    await message.answer(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:", reply_markup=city_kb())


@router.callback_query(CreateShowFSM.select_city, CityCb.filter())
async def process_city_select(callback: CallbackQuery, callback_data: CityCb, state: FSMContext):
    await callback.answer()
    if callback_data.value == "custom":
        await state.set_state(CreateShowFSM.city)
        await callback.message.edit_text(f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Введи название города:", reply_markup=fsm_cancel_kb())
    else:
        await state.update_data(city=callback_data.value)
        await state.set_state(CreateShowFSM.max_seats)
        await callback.message.edit_text(f"✅ Город: {callback_data.value}")
        await callback.message.answer(f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.city, F.text)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text.strip())
    await state.set_state(CreateShowFSM.max_seats)
    await message.answer(f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.max_seats, F.text)
async def process_max_seats(message: Message, state: FSMContext):
    try:
        seats = int(message.text.strip())
        if seats <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное число мест:", reply_markup=fsm_cancel_kb())
        return
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_CUSTOM)
    await state.update_data(max_seats=seats)
    await state.set_state(CreateShowFSM.poster_text)
    logger.info("create_show moved to poster_text state total=%s", total)
    await message.answer(
        f"{_progress(total - 2, total)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
    )


@router.callback_query(CreateShowFSM.poster_text, F.data == "fsm_skip_poster_text")
async def skip_poster_text(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.update_data(poster_text=None)
    await state.set_state(CreateShowFSM.poster_image)
    await callback.message.edit_text("⏭ Текст афиши пропущен.")
    await callback.message.answer(
        f"{_progress(total - 1, total)}Отправь изображение афиши:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )


@router.message(CreateShowFSM.poster_text, F.text)
async def process_poster_text(message: Message, state: FSMContext):
    text = message.text.strip()
    logger.info("create_show poster_text received length=%s", len(text))
    error = _validate_poster_text(text)
    if error:
        await message.answer(error, reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"))
        return
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.update_data(poster_text=text)
    await state.set_state(CreateShowFSM.poster_image)
    await message.answer(
        f"{_progress(total - 1, total)}Отправь изображение афиши:",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )


@router.message(CreateShowFSM.poster_text)
async def process_poster_text_fallback(message: Message, state: FSMContext):
    if message.text is not None:
        return
    await message.answer(
        "Отправь текст афиши или нажми ⏭ Пропустить.",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
    )


@router.callback_query(CreateShowFSM.poster_image, F.data == "fsm_skip_poster_image")
async def skip_poster_image(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(poster_file_id=None)
    await callback.message.edit_text("⏭ Изображение пропущено.")
    # proceed to optional registrar selection
    await _ask_registrar(callback.message, state, callback._current_bot)


@router.message(CreateShowFSM.poster_image, F.photo)
async def process_poster_image(message: Message, state: FSMContext):
    file_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=file_id)
    # proceed to optional registrar selection
    await _ask_registrar(message, state, message.bot)


@router.message(CreateShowFSM.poster_image)
async def process_poster_image_invalid(message: Message, state: FSMContext):
    await message.answer(
        "Отправь фото или нажми ⏭ Пропустить",
        reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
    )


async def _make_calendar(session: AsyncSession) -> RuCalendar:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from db.models import Show, User
    result = await session.execute(
        select(Show).options(selectinload(Show.creator))
    )
    shows = result.scalars().all()
    busy: dict[_date, list[str]] = {}
    for s in shows:
        d = s.show_date.date()
        creator = s.creator
        if creator:
            name = creator.first_name or creator.username or f"id{creator.telegram_id}"
        else:
            name = "?"
        busy.setdefault(d, []).append(f"{s.title} ({name})")
    return RuCalendar(busy)



def _preview_from_data(data: dict) -> str:
    location = data.get("location", "")
    location_url = data.get("location_url")
    city = data.get("city", "")
    if location_url:
        location_line = f'📍 <a href="{location_url}">{location}</a>, {city}'
    else:
        location_line = f"📍 {location}, {city}"

    show_date = data.get("show_date")
    if show_date:
        date_str = _fmt_date(show_date)
    else:
        date_str = data.get("show_date_str", "")

    registrar_name = data.get("registrar_name") or "(через бот)"
    poster = data.get("poster_text") or ""
    lines = [
        f"🎭 <b>{data.get('title', '')}</b>",
        f"📅 {date_str}",
        location_line,
        f"👥 Ответственный за записи: {registrar_name}",
    ]
    if poster:
        lines += ["", poster]
    return "\n".join(lines)


async def _show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.set_state(CreateShowFSM.confirm)

    preview = _preview_from_data(data)
    kb = confirm_with_back_kb("admin_confirm_create", "admin_cancel_create")
    header = f"{_progress(total, total)}👁 <b>Так будет выглядеть анонс:</b>\n\n"

    file_id = data.get("poster_file_id")
    if file_id:
        await message.answer_photo(
            photo=file_id,
            caption=header + preview,
            reply_markup=kb,
        )
    else:
        await message.answer(header + preview, reply_markup=kb)


async def _ask_registrar(message: Message, state: FSMContext, bot: Bot):
    """Prompt to optionally choose a registrar (organizer/admin) or skip."""
    await state.set_state(CreateShowFSM.registrar)
    # fetch organizers/admins
    async with AsyncSessionLocal() as session:
        organizers = await crud.get_all_organizers(session)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    # build message with clickable t.me links when username exists
    lines = []
    for idx, u in enumerate(organizers, start=1):
        if u.username:
            lines.append(f"{idx}. <a href=\"https://t.me/{u.username}\">{u.first_name or ('@'+u.username)}</a>")
        else:
            lines.append(f"{idx}. {u.first_name or ('id'+str(u.telegram_id))}")

    text = "Выбери ответственного за записи (опционально):\n\n" + "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for u in organizers:
        label = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        kb.button(text=label, callback_data=f"registrar:{u.id}")
    kb.button(text="Пропустить (через бот)", callback_data="registrar:0")
    kb.button(text="◀️ Назад", callback_data="fsm_back")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "fsm_back")
async def fsm_back(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)

    if current == CreateShowFSM.title:
        await state.set_state(CreateShowFSM.team_name)
        await callback.message.edit_text(
            f"{_progress(1)}Выбери команду из списка или введи своё название:",
            reply_markup=team_kb(),
        )

    elif current == CreateShowFSM.show_date:
        await state.set_state(CreateShowFSM.title)
        await callback.message.edit_text(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())

    elif current == CreateShowFSM.select_time:
        now = datetime.utcnow()
        await state.set_state(CreateShowFSM.show_date)
        await callback.message.edit_text(
            f"{_progress(3)}Выбери дату шоу:",
            reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
        )

    elif current == CreateShowFSM.select_venue:
        await state.set_state(CreateShowFSM.select_time)
        await callback.message.edit_text(
            f"{_progress(3)}Выбери время начала:",
            reply_markup=_time_kb(),
        )

    elif current == CreateShowFSM.location:
        venues = await crud.list_venues(session)
        await state.set_state(CreateShowFSM.select_venue)
        await callback.message.edit_text(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))

    elif current == CreateShowFSM.location_url:
        await state.set_state(CreateShowFSM.location)
        await callback.message.edit_text(
            f"{_progress(4, _TOTAL_STEPS_CUSTOM)}Введи название площадки/театра:",
            reply_markup=fsm_cancel_kb(),
        )

    elif current in (CreateShowFSM.select_city, CreateShowFSM.city):
        await state.set_state(CreateShowFSM.location_url)
        await callback.message.edit_text(
            f"{_progress(5, _TOTAL_STEPS_CUSTOM)}Введи ссылку на Google Maps для этой площадки:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
        )

    elif current == CreateShowFSM.max_seats:
        await state.set_state(CreateShowFSM.select_city)
        await callback.message.edit_text(
            f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:",
            reply_markup=city_kb(),
        )

    elif current == CreateShowFSM.poster_text:
        if total == _TOTAL_STEPS_PRESET:
            venues = await crud.list_venues(session)
            await state.set_state(CreateShowFSM.select_venue)
            await callback.message.edit_text(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))
        else:
            await state.set_state(CreateShowFSM.max_seats)
            await callback.message.edit_text(
                f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):",
                reply_markup=fsm_cancel_kb(),
            )

    elif current == CreateShowFSM.poster_image:
        await state.set_state(CreateShowFSM.poster_text)
        await callback.message.edit_text(
            f"{_progress(total - 1, total)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
        )

    elif current == CreateShowFSM.registrar:
        await state.set_state(CreateShowFSM.poster_image)
        await callback.message.answer(
            f"{_progress(total - 1, total)}Отправь изображение афиши:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
        )

    elif current == CreateShowFSM.confirm:
        await state.set_state(CreateShowFSM.poster_image)
        await callback.message.answer(
            f"{_progress(total - 1, total)}Отправь изображение афиши:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
        )

    else:
        await callback.answer("Это первый шаг, назад некуда.", show_alert=True)


@router.callback_query(F.data == "fsm_cancel")
async def fsm_cancel(callback: CallbackQuery, state: FSMContext, is_super_admin: bool = False):
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text("❌ Создание шоу отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(CreateShowFSM.registrar, lambda q: q.data and q.data.startswith("registrar:"))
async def process_registrar_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    _, raw = callback.data.split(":", 1)
    try:
        uid = int(raw)
    except ValueError:
        uid = 0
    if uid == 0:
        await state.update_data(registrar_id=None, registrar_name=None)
    else:
        # store chosen registrar id and name for preview
        async with AsyncSessionLocal() as session:
            u = await crud.get_user_by_id(session, uid) if hasattr(crud, 'get_user_by_id') else None
        name = None
        if u:
            name = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        await state.update_data(registrar_id=uid, registrar_name=name)
    # proceed to confirm
    await _show_confirm(callback.message, state)


@router.callback_query(CreateShowFSM.confirm, F.data == "admin_confirm_create")
async def confirm_create(callback: CallbackQuery, state: FSMContext, bot: Bot, public_bot: Bot, session: AsyncSession, is_super_admin: bool = False):
    data = await state.get_data()
    await callback.answer()

    tg_id = callback.from_user.id
    user = await crud.get_user_by_telegram_id(session, tg_id)
    if user is None:
        user = await crud.upsert_user(session, tg_id, callback.from_user.username,
                                      callback.from_user.first_name, callback.from_user.last_name)
    show = await crud.create_show(
        session,
        title=data["title"],
        team_name=data["team_name"],
        show_date=data["show_date"],
        location=data["location"],
        location_url=data.get("location_url"),
        city=data["city"],
        poster_text=data.get("poster_text"),
        poster_file_id=data.get("poster_file_id"),
        max_seats=data["max_seats"],
        creator_id=user.id,
        registrar_id=data.get("registrar_id"),
    )
    logger.info("admin %s created show id=%s title=%s", tg_id, show.id, data.get('title'))

    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"✅ Шоу <b>{data['title']}</b> создано и пока нигде не опубликовано.",
        reply_markup=main_menu_kb(),
    )
    await callback.message.answer(
        "Что делаем дальше:\n"
        "• 👁 <b>Превью</b> — проверь, как выглядит анонс\n"
        "• 📢 <b>Анонс</b> — отправь в канал, когда готов\n"
        "• 🔗 <b>Ссылка</b> — поделись вручную",
        reply_markup=show_created_kb(show.id),
    )
    # Cache poster for public bot so it can display it via deep links
    if show.poster_file_id:
        pub_file_id = await cache_poster_for_public_bot(bot, public_bot, show.poster_file_id, tg_id)
        if pub_file_id:
            async with AsyncSessionLocal() as extra_session:
                await crud.update_show(extra_session, show.id, pub_poster_file_id=pub_file_id)


@router.callback_query(CreateShowFSM.confirm, F.data == "admin_cancel_create")
async def cancel_create(callback: CallbackQuery, state: FSMContext, is_super_admin: bool = False):
    await state.clear()
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("❌ Создание отменено.", reply_markup=main_menu_kb())


# ── List & detail ────────────────────────────────────────────────────────────

_STATUS_LABELS = {"all": "Все", "active": "Активные", "past": "Прошедшие", "cancelled": "Отменённые"}


async def _render_shows_list(msg, state: FSMContext, session: AsyncSession, edit: bool = False, can_manage: bool = True):
    data = await state.get_data()
    f_status = data.get("f_status", "active")
    f_team = data.get("f_team")
    f_year = data.get("f_year")

    shows = await crud.list_all_shows(session, status=f_status, team=f_team, year=f_year)

    parts = [f"📋 <b>Все шоу</b>"]
    filters = []
    if f_status != "all":
        filters.append(_STATUS_LABELS[f_status])
    if f_team:
        filters.append(f_team)
    if f_year:
        filters.append(str(f_year))
    if filters:
        parts.append(f" · {', '.join(filters)}")
    parts.append(f" ({len(shows)}):" if shows else ":")
    text = "".join(parts) if shows else "Нет шоу по выбранному фильтру."

    kb = shows_list_kb(shows, can_manage=can_manage)
    try:
        if edit:
            await msg.edit_text(text, reply_markup=kb)
        else:
            await msg.answer(text, reply_markup=kb)
    except Exception:
        await msg.answer(text, reply_markup=kb)


@router.callback_query(F.data == "admin_shows_list")
async def cmd_shows_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await callback.answer()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(callback.message, state, session, edit=True, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(F.data == "admin_shows_filter")
async def shows_filter_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    current = {k: data.get(k) for k in ("status", "team", "year")
               if data.get(k) or k == "status"}
    current.setdefault("status", data.get("f_status", "all"))
    current["team"] = data.get("f_team")
    current["year"] = data.get("f_year")
    await callback.message.edit_text(
        "🔍 <b>Фильтр шоу</b>\n\nНажми чтобы переключить значение:",
        reply_markup=shows_filter_kb(current),
    )


@router.callback_query(AdminFilterStatusCb.filter())
async def filter_set_status(callback: CallbackQuery, callback_data: AdminFilterStatusCb, state: FSMContext):
    new_status = callback_data.status
    await state.update_data(f_status=new_status)
    await callback.answer(f"Статус: {_STATUS_LABELS[new_status]}")
    data = await state.get_data()
    current = {"status": new_status, "team": data.get("f_team"), "year": data.get("f_year")}
    try:
        await callback.message.edit_reply_markup(reply_markup=shows_filter_kb(current))
    except Exception:
        pass


@router.callback_query(F.data == "admin_filter_reset")
async def filter_reset(callback: CallbackQuery, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.update_data(f_status="active", f_team=None, f_year=None)
    await callback.answer("Фильтр сброшен")
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(callback.message, state, session, edit=True, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(F.data == "admin_filter_team")
async def filter_set_team(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(EditShowFSM.field)
    await state.update_data(_filter_mode="team")
    await callback.message.edit_text(
        "Введи название команды для фильтра (или /skip чтобы убрать):"
    )


@router.callback_query(F.data == "admin_filter_year")
async def filter_set_year(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(EditShowFSM.field)
    await state.update_data(_filter_mode="year")
    await callback.message.edit_text(
        "Введи год (например 2026), или /skip чтобы убрать фильтр по году:"
    )


@router.message(EditShowFSM.field, F.text)
async def filter_input(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    mode = data.get("_filter_mode")
    if not mode:
        return
    raw = message.text.strip()
    if raw == "/skip":
        await state.update_data(**{f"f_{mode}": None, "_filter_mode": None})
    elif mode == "year":
        try:
            year = int(raw)
            if not 2000 <= year <= 2100:
                raise ValueError
            await state.update_data(f_year=year, _filter_mode=None)
        except ValueError:
            await message.answer("Введи корректный год (например 2026) или /skip:")
            return
    else:
        await state.update_data(f_team=raw, _filter_mode=None)
    await state.set_state(None)
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(message, state, session, edit=False, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(AdminShowActionCb.filter(F.action == "open"))
async def show_detail(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.edit_text("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    tg_id = callback.from_user.id
    user = await crud.get_user_by_telegram_id(session, tg_id)

    is_creator = (show.creator and show.creator.telegram_id == tg_id) or tg_id in ADMIN_ID_LIST
    if user and user.role == UserRole.admin:
        is_creator = True

    seats_left = show.max_seats - active_count
    creator = show.creator
    creator_label = ""
    if creator:
        name = creator.first_name or creator.username or str(creator.telegram_id)
        uname = f" (@{creator.username})" if creator.username else ""
        creator_label = f"👤 Создатель: {name}{uname}\n"

    registrar = show.registrar
    registrar_label = ""
    if registrar:
        name = registrar.first_name or registrar.username or str(registrar.telegram_id)
        uname = f" (@{registrar.username})" if registrar.username else ""
        registrar_label = f"👥 Ответственный за записи: {name}{uname}\n"
    else:
        registrar_label = "👥 Ответственный за записи: (через бот)\n"

    text = (
        f"🎭 <b>{show.title}</b>\n"
        f"👥 Команда: {show.team_name}\n"
        f"📅 {show.show_date.strftime('%d.%m.%Y %H:%M')}\n"
        f"🏙 {show.city} | 📍 {show.location}\n"
        f"🪑 Мест: {seats_left}/{show.max_seats}\n"
        f"{creator_label}"
        f"{registrar_label}"
    )
    if show.poster_text:
        text += f"\n📝 {show.poster_text}"

    from aiogram.exceptions import TelegramBadRequest
    can_delete = tg_id in ADMIN_ID_LIST
    try:
        await callback.message.edit_text(text, reply_markup=show_detail_kb(show, is_creator, can_delete=can_delete))
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=show_detail_kb(show, is_creator, can_delete=can_delete))


@router.callback_query(AdminShowActionCb.filter(F.action == "preview"))
async def show_announcement_preview(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from scheduler.jobs import _register_button
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ Назад", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())

    preview_text = build_announcement_text(show)
    reg_btn = _register_button(show)
    preview_kb = InlineKeyboardBuilder()
    if reg_btn:
        for row in reg_btn.inline_keyboard:
            for btn in row:
                preview_kb.button(text=btn.text, url=btn.url)
    preview_kb.button(text="◀️ Назад", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    preview_kb.adjust(1)

    if show.poster_file_id:
        await callback.message.answer_photo(
            show.poster_file_id,
            caption=f"👁 <b>Превью анонса:</b>\n\n{preview_text}",
            reply_markup=preview_kb.as_markup(),
        )
    else:
        await callback.message.answer(
            f"👁 <b>Превью анонса:</b>\n\n{preview_text}",
            reply_markup=preview_kb.as_markup(),
        )


def _show_deep_link(show_id: int) -> str:
    return f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show_id}"


@router.callback_query(AdminShowActionCb.filter(F.action == "link"))
async def send_show_link(callback: CallbackQuery, callback_data: AdminShowActionCb):
    show_id = callback_data.show_id
    await callback.answer()
    link = _show_deep_link(show_id)
    await callback.message.answer(
        f"🔗 <b>Ссылка на запись:</b>\n\n"
        f"<code>{link}</code>\n\n"
        f"Вставь в сторис через стикер-ссылку или напиши в комментарии под постом.",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "qr"))
async def send_show_qr(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    link = _show_deep_link(show_id)
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    date_str = show.show_date.strftime("%d.%m.%Y")
    caption = (
        f"📱 <b>QR-код для {show.title}</b>\n"
        f"📅 {date_str}\n\n"
        f"Пост в Instagram → человек наводит камеру → "
        f"переходит в бот → видит шоу → записывается."
    )
    await callback.message.answer_photo(
        BufferedInputFile(buf.read(), filename="qr.png"),
        caption=caption,
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "announce"))
async def send_manual_announcement(callback: CallbackQuery, callback_data: AdminShowActionCb, bot: Bot, public_bot: Bot, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return
    if not show.is_active:
        await callback.message.answer("❌ Шоу отменено — анонс нельзя отправить.")
        return

    missing = []
    if not show.poster_text:
        missing.append("📝 текст афиши")
    if not show.poster_file_id:
        missing.append("🖼 изображение")
    if missing:
        await callback.answer(
            f"Нельзя отправить анонс — не заполнено: {', '.join(missing)}.\n"
            "Заполни через ✏️ Редактировать.",
            show_alert=True,
        )
        return

    text = build_announcement_text(show)
    try:
        msg_id = await send_to_channel(public_bot, bot, show, text)
        if msg_id:
            await crud.save_channel_message_id(session, show_id, msg_id)
        await callback.message.answer("✅ Анонс отправлен в канал!")
        logger.info("manual announcement sent show_id=%s channel_msg_id=%s by admin=%s", show_id, msg_id, callback.from_user.id)
    except Exception as e:
        logger.error("Failed to send manual announcement: %s", e)
        await callback.message.answer(f"❌ Ошибка при отправке: {e}")


@router.callback_query(AdminShowActionCb.filter(F.action == "remind"))
async def remind_viewers(callback: CallbackQuery, callback_data: AdminShowActionCb, public_bot: Bot, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return
    if not show.is_active:
        await callback.message.answer("❌ Шоу отменено — напоминания нельзя отправить.")
        return
    users = await crud.get_registered_users_for_show(session, show_id)
    channel_msg_id = await crud.get_last_channel_message_id(session, show_id)

    if not users:
        await callback.message.answer("Нет записавшихся зрителей.")
        return

    date_str = show.show_date.strftime("%d.%m.%Y %H:%M")
    location_line = _location_line(show)
    reminder_text = (
        f"🔔 Напоминание!\n\n"
        f"Ты записан(а) на шоу <b>{show.title}</b>\n"
        f"📅 {date_str}\n"
        f"{location_line}"
    )

    post_url = None
    if channel_msg_id:
        ch = settings.ANNOUNCEMENT_CHANNEL_ID
        if ch.startswith("@"):
            post_url = f"https://t.me/{ch.lstrip('@')}/{channel_msg_id}"
        else:
            post_url = f"https://t.me/c/{str(ch).replace('-100', '').lstrip('-')}/{channel_msg_id}"

    sent, failed = 0, 0
    for user in users:
        try:
            kwargs = {}
            if post_url:
                kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
            await public_bot.send_message(user.telegram_id, reminder_text, **kwargs)
            sent += 1
        except Exception:
            failed += 1

    result = f"✅ Напоминание отправлено {sent} зрител{'ю' if sent == 1 else 'ям'}."
    if failed:
        result += f"\n⚠️ Не доставлено: {failed} (бот заблокирован или не начат)."
    await callback.message.answer(result)


# ── Free advertising ─────────────────────────────────────────────────────────

@router.callback_query(AdminShowActionCb.filter(F.action == "free_ad"))
async def free_ad(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from scheduler.jobs import build_announcement_text
    from config import settings

    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    channels = await crud.get_active_ad_channels(session)
    logger.info("admin %s opened free_ad for show_id=%s channels_count=%s", callback.from_user.id, show_id, len(channels))
    if not channels:
        await callback.message.answer(
            "Нет активных рекламных каналов.\n"
            "Добавь их в Настройки → 📣 Рекламные каналы."
        )
        return

    text = build_announcement_text(show)

    reg_url = f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show.id}"
    reg_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Записаться на шоу", url=reg_url)
    ]])

    await callback.message.answer(text, reply_markup=reg_kb)

    nav_builder = InlineKeyboardBuilder()
    for ch in channels:
        nav_builder.button(text=f"➡️ {ch.username}", url=ch.url)
    # add a back button to return to the show detail view
    nav_builder.button(text="◀️ Назад", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    nav_builder.adjust(1)

    await callback.message.answer(
        "⬆️ <b>Перешли сообщение выше</b> в нужный канал:\n"
        "(нажми «Переслать» → выбери канал из списка)",
        reply_markup=nav_builder.as_markup(),
    )


# ── Cancel show ──────────────────────────────────────────────────────────────

@router.callback_query(AdminShowActionCb.filter(F.action == "cancel"))
async def cancel_show_confirm(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    await callback.message.edit_text(
        f"🚫 <b>Отменить шоу?</b>\n\n"
        f"🎭 {show.title}\n"
        f"📅 {show.show_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Все записанные зрители получат уведомление об отмене.\n"
        f"В канал будет отправлено сообщение с перечёркнутым анонсом.\n\n"
        f"<b>Это действие нельзя отменить.</b>",
        reply_markup=confirm_kb(AdminShowActionCb(action="confirm_cancel", show_id=show_id).pack(), AdminShowActionCb(action="open", show_id=show_id).pack()),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "delete"))
async def delete_show_confirm(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    await callback.answer()
    if callback.from_user.id not in ADMIN_ID_LIST:
        await callback.answer("Удалять шоу могут только администраторы.", show_alert=True)
        return

    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    await callback.message.edit_text(
        f"🗑 <b>Удалить шоу навсегда?</b>\n\n"
        f"🎭 {show.title}\n"
        f"📅 {show.show_date.strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Это удалит все записи, лог анонсов и связанные данные.\n"
        f"<b>Действие необратимо.</b>",
        reply_markup=confirm_kb(AdminShowActionCb(action="confirm_delete", show_id=show_id).pack(), AdminShowActionCb(action="open", show_id=show_id).pack()),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "confirm_delete"))
async def delete_show_execute(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    await callback.answer()
    if callback.from_user.id not in ADMIN_ID_LIST:
        await callback.answer("Удалять шоу могут только администраторы.", show_alert=True)
        return

    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.edit_text("Шоу не найдено.")
        return

    deleted = await crud.delete_show(session, show_id)
    if not deleted:
        await callback.message.edit_text("Не удалось удалить шоу — возможно, есть связанные записи. Попробуйте позже.")
        return

    await callback.message.edit_text(f"🗑 Шоу <b>{show.title}</b> удалено навсегда.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "confirm_cancel"))
async def cancel_show_execute(callback: CallbackQuery, callback_data: AdminShowActionCb, bot: Bot, public_bot: Bot, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None or not show.is_active:
        await callback.message.edit_text("Шоу не найдено или уже отменено.")
        return
    was_announced = await crud.has_any_announcement_been_sent(session, show_id)
    reply_to = await crud.get_last_channel_message_id(session, show_id)
    users = await crud.get_registered_users_for_show(session, show_id)
    await crud.update_show(session, show_id, is_active=False)
    logger.info("show cancelled id=%s by admin=%s", show_id, callback.from_user.id)

    await callback.message.edit_text(f"🚫 Шоу <b>{show.title}</b> отменено.")

    if was_announced:
        channel_text = (
            f"🚫 <b>Шоу отменено</b>\n\n"
            f"🎭 <s>{show.title}</s>\n"
            f"📅 <s>{show.show_date.strftime('%d.%m.%Y %H:%M')}</s>\n"
            f"📍 <s>{show.location}, {show.city}</s>\n\n"
            f"Приносим извинения за неудобства. Следите за новыми анонсами!"
        )
        try:
            await send_to_channel(
                public_bot, bot, show, channel_text,
                with_button=False, reply_to_message_id=reply_to,
            )
            logger.info("posted cancellation to channel for show %s reply_to=%s", show_id, reply_to)
        except Exception:
            logger.exception("Failed to post cancellation to channel for show %s", show_id)

    # Personal DMs
    personal_text = (
        f"❌ <b>Шоу отменено</b>\n\n"
        f"К сожалению, мероприятие, на которое ты записан(а), отменено:\n\n"
        f"🎭 <b>{show.title}</b>\n"
        f"📅 {show.show_date.strftime('%d.%m.%Y %H:%M')}\n"
        f"{_location_line(show)}\n\n"
        f"Приносим извинения! Следи за новыми анонсами 🎭"
    )
    ch = settings.ANNOUNCEMENT_CHANNEL_ID
    channel_url = f"https://t.me/{ch.lstrip('@')}" if ch.startswith("@") else None
    cancel_kb = None
    if channel_url:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)
        ]])
    sent, failed = 0, 0
    for user in users:
        try:
            await public_bot.send_message(user.telegram_id, personal_text, reply_markup=cancel_kb)
            sent += 1
        except Exception:
            failed += 1

    logger.info("cancellation notifications for show %s sent=%s failed=%s", show_id, sent, failed)

    result = f"✅ Уведомление об отмене отправлено {sent} зрител{'ю' if sent == 1 else 'ям'}."
    if failed:
        result += f"\n⚠️ Не доставлено: {failed}."
    await callback.message.answer(result)


@router.callback_query(AdminShowActionCb.filter(F.action == "restore"))
async def restore_show(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None or show.is_active:
        await callback.message.answer("Шоу не найдено или уже активно.")
        return
    await crud.update_show(session, show_id, is_active=True)
    logger.info("restored show id=%s by admin=%s", show_id, callback.from_user.id)

    show = await crud.get_show(session, show_id)

    tg_id = callback.from_user.id
    is_creator = (show.creator and show.creator.telegram_id == tg_id) or tg_id in ADMIN_ID_LIST
    kb = show_detail_kb(show, is_creator, can_delete=(callback.from_user.id in ADMIN_ID_LIST))

    await callback.message.edit_text(
        f"✅ Шоу <b>{show.title}</b> восстановлено и снова активно.",
        reply_markup=kb,
    )


# ── Edit flow ────────────────────────────────────────────────────────────────

@router.callback_query(AdminShowActionCb.filter(F.action == "edit"))
async def start_edit(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext):
    show_id = callback_data.show_id
    await callback.answer()
    await state.set_state(EditShowFSM.field)
    await state.update_data(editing_show_id=show_id)
    await callback.message.edit_text(
        "Выбери поле для редактирования:",
        reply_markup=edit_show_fields_kb(show_id),
    )


@router.callback_query(AdminShowFieldCb.filter())
async def choose_edit_field(callback: CallbackQuery, callback_data: AdminShowFieldCb, state: FSMContext, session: AsyncSession):
    show_id = callback_data.show_id
    field = callback_data.field
    await callback.answer()
    await state.set_state(EditShowFSM.new_value)
    await state.update_data(editing_show_id=show_id, editing_field=field)

    show = await crud.get_show(session, show_id)

    prompts = {
        "title": "Введи новое название шоу:",
        "team_name": "Введи новое название команды:",
        "show_date": "Введи новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):",
        "city": "Введи новый город:",
        "location": "Введи новое название площадки:",
        "location_url": "Введи ссылку на Google Maps (или /skip чтобы убрать):",
        "max_seats": "Введи новое количество мест:",
        "registrar_id": "Выбери ответственного за записи:",
        "poster_text": "Введи новый текст афиши (или /skip чтобы очистить):",
        "poster_file_id": "Отправь новое изображение афиши:",
    }

    current_values = {
        "title": show.title,
        "team_name": show.team_name,
        "show_date": show.show_date.strftime("%d.%m.%Y %H:%M"),
        "city": show.city,
        "location": show.location,
        "location_url": show.location_url or "(не указана)",
        "max_seats": str(show.max_seats),
        "registrar_id": (show.registrar.first_name or (('@' + show.registrar.username) if show.registrar.username else f'id{show.registrar.telegram_id}')) if show and show.registrar else "(не указан)",
        "poster_text": show.poster_text or "(не указан)",
    } if show else {}

    prompt = prompts.get(field, "Введи новое значение:")
    current = current_values.get(field)

    if field == "registrar_id":
        await _ask_edit_registrar(callback.message, state)
        return

    if current and field != "poster_file_id":
        text = f"{prompt}\n\n<b>Текущее значение:</b>\n<code>{current}</code>"
    else:
        text = prompt

    if field == "show_date":
        text += "\n\n⚠️ <i>Все записанные зрители получат уведомление. В канал будет отправлено сообщение об изменении.</i>"

    await callback.message.edit_text(text)


async def _ask_edit_registrar(message: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    show_id = data.get("editing_show_id")
    async with AsyncSessionLocal() as session:
        show = await crud.get_show(session, show_id) if show_id else None
        organizers = await crud.get_all_organizers(session)

    lines = []
    for idx, u in enumerate(organizers, start=1):
        if u.username:
            lines.append(f"{idx}. <a href=\"https://t.me/{u.username}\">{u.first_name or ('@'+u.username)}</a>")
        else:
            lines.append(f"{idx}. {u.first_name or ('id'+str(u.telegram_id))}")

    text = "Выбери ответственного за записи (или пропусти):\n\n" + "\n".join(lines)
    if show and show.registrar:
        current_name = show.registrar.first_name or (('@' + show.registrar.username) if show.registrar.username else f'id{show.registrar.telegram_id}')
        text += f"\n\nТекущий: <b>{current_name}</b>"

    kb = InlineKeyboardBuilder()
    for u in organizers:
        label = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        kb.button(text=label, callback_data=f"registrar:{u.id}")
    kb.button(text="Пропустить (через бот)", callback_data="registrar:0")
    kb.button(text="◀️ Назад", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    kb.adjust(1)

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(EditShowFSM.new_value, lambda q: q.data and q.data.startswith("registrar:"))
async def edit_process_registrar_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    data = await state.get_data()
    if data.get("editing_field") != "registrar_id":
        return
    _, raw = callback.data.split(":", 1)
    try:
        value = int(raw)
    except ValueError:
        value = None
    await _apply_edit(callback.message, state, session, None if value == 0 else value)


@router.message(EditShowFSM.new_value, F.photo)
async def save_edit_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, public_bot: Bot):
    data = await state.get_data()
    if data.get("editing_field") != "poster_file_id":
        await message.answer("Ожидался текст. Введи текстовое значение:")
        return
    await _apply_edit(message, state, session, message.photo[-1].file_id, bot=bot, public_bot=public_bot)


@router.message(EditShowFSM.new_value, F.text)
async def save_edit_text(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, public_bot: Bot):
    data = await state.get_data()
    field = data.get("editing_field")
    raw = message.text.strip()

    if field == "show_date":
        try:
            value = datetime.strptime(raw, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("Неверный формат. Введи как ДД.ММ.ГГГГ ЧЧ:ММ:")
            return
        if value <= datetime.utcnow():
            await message.answer("❌ Дата в прошлом. Введи будущую дату:")
            return
    elif field == "max_seats":
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введи положительное целое число:")
            return
    elif field == "title":
        if len(raw) < 2:
            await message.answer("Название слишком короткое (минимум 2 символа):")
            return
        value = raw
    elif field == "team_name":
        if len(raw) < 2:
            await message.answer("Название команды слишком короткое (минимум 2 символа):")
            return
        value = raw
    elif field == "poster_text":
        if raw == "/skip":
            value = None
        else:
            error = _validate_poster_text(raw)
            if error:
                await message.answer(error)
                return
            value = raw
    elif field == "location_url":
        if raw == "/skip":
            value = None
        elif not _is_google_maps_url(raw):
            await message.answer(
                "Это не ссылка на Google Maps. Введи корректную ссылку или /skip чтобы убрать:"
            )
            return
        else:
            value = raw
    else:
        value = raw

    await _apply_edit(message, state, session, value, bot=bot if field == "show_date" else None,
                      public_bot=public_bot if field == "show_date" else None)


async def _apply_edit(message: Message, state: FSMContext, session: AsyncSession, value, bot: Bot = None, public_bot: Bot = None):
    data = await state.get_data()
    show_id = data["editing_show_id"]
    field = data["editing_field"]
    await state.clear()

    old_show = await crud.get_show(session, show_id)
    old_date = old_show.show_date if old_show else None
    show = await crud.update_show(session, show_id, **{field: value})

    logger.info("updated show id=%s field=%s by admin=%s", show_id, field, message.from_user.id)

    if show is None:
        await message.answer("Шоу не найдено.")
        return

    # When poster is updated, re-cache for public bot
    if field == "poster_file_id" and value and bot and public_bot:
        pub_file_id = await cache_poster_for_public_bot(bot, public_bot, value, message.from_user.id)
        if pub_file_id:
            async with AsyncSessionLocal() as extra_session:
                await crud.update_show(extra_session, show_id, pub_poster_file_id=pub_file_id)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    await message.answer("✅ Поле обновлено!", reply_markup=back_kb.as_markup())

    if field == "show_date" and old_date and public_bot and bot:
        await _notify_date_change(show, old_date, bot, public_bot)


async def _notify_date_change(show, old_date, admin_bot: Bot, public_bot: Bot):
    from db import crud as _crud
    old_str = old_date.strftime("%d.%m.%Y %H:%M")
    new_str = show.show_date.strftime("%d.%m.%Y %H:%M")

    async with AsyncSessionLocal() as session:
        reply_to = await _crud.get_last_channel_message_id(session, show.id)

    channel_text = (
        f"⚠️ <b>Изменение даты!</b>\n\n"
        f"📅 Было: <s>{old_str}</s>\n"
        f"📅 Стало: {new_str}\n\n"
        f"Обновлённый анонс:"
    )
    try:
        await send_to_channel(
            public_bot, admin_bot, show, channel_text,
            reply_to_message_id=reply_to,
        )
    except Exception:
        logger.exception("Failed to post date-change to channel")

    new_date_str = show.show_date.strftime("%d.%m.%Y %H:%M")
    location_line = _location_line(show)
    personal_text = (
        f"⚠️ <b>Дата шоу изменилась!</b>\n\n"
        f"Ты записан(а) на шоу <b>{show.title}</b>\n"
        f"📅 Было: <s>{old_str}</s>\n"
        f"📅 Стало: {new_date_str}\n"
        f"{location_line}"
    )

    async with AsyncSessionLocal() as session:
        users = await crud.get_registered_users_for_show(session, show.id)
        channel_msg_id = await crud.get_last_channel_message_id(session, show.id)

    post_url = None
    if channel_msg_id:
        ch = settings.ANNOUNCEMENT_CHANNEL_ID
        if ch.startswith("@"):
            post_url = f"https://t.me/{ch.lstrip('@')}/{channel_msg_id}"
        else:
            post_url = f"https://t.me/c/{str(ch).replace('-100', '').lstrip('-')}/{channel_msg_id}"

    sent, failed = 0, 0
    for user in users:
        try:
            kwargs = {}
            if post_url:
                kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
            await public_bot.send_message(user.telegram_id, personal_text, **kwargs)
            sent += 1
        except Exception:
            failed += 1

    logger.info("Date-change notifications: sent=%s failed=%s show=%s", sent, failed, show.id)
