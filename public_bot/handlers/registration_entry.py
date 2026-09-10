from __future__ import annotations

from app_logging import get_project_logger
from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession
from db import crud
from db.models import User
from admin_bot.callbacks import AdminShowActionCb
from public_bot.keyboards.inline import confirm_registration_kb, show_detail_kb, registration_success_kb, guests_kb, attendance_kb, calendar_kb, registrar_username
from public_bot.callbacks import RegisterCb, ConfirmRegCb, GuestsCb, GuestsCustomCb, RemindToggleCb, EditGuestsCb, AttendanceCb, CalendarCb, FeedbackCb, WaitlistCb
from html_utils import h
from time_utils import format_local, utc_now

router = Router()
logger = get_project_logger(__name__)



@router.callback_query(F.data == "pub_registration_closed")
async def registration_closed(callback: CallbackQuery):
    await callback.answer("Запись на это шоу уже закрыта.", show_alert=True)


@router.callback_query(WaitlistCb.filter())
async def join_show_waitlist(callback: CallbackQuery, callback_data: WaitlistCb, db_user: User, session: AsyncSession):
    show = await crud.get_show(session, callback_data.show_id)
    if show is None:
        await callback.answer("Шоу не найдено.", show_alert=True)
        return
    entry, position = await crud.join_waitlist(
        session, show.id, db_user.id, db_user.first_name or db_user.username or "Зритель",
    )
    if entry is None:
        await callback.answer("Лист ожидания уже недоступен.", show_alert=True)
        return
    await callback.answer("Добавлено")
    await callback.message.answer(
        f"⏳ Ты в листе ожидания на <b>{h(show.title)}</b>. Твоя позиция: <b>{position}</b>.\n\n"
        "Если освободится место, бот запишет тебя автоматически и пришлёт сообщение."
    )


class RegisterFSM(StatesGroup):
    enter_name = State()
    choose_guests = State()
    enter_guests_count = State()
    confirm = State()
    edit_guests_count = State()
    feedback_comment = State()


def _guests_label(guests: int) -> str:
    if guests == 0:
        return ""
    if guests == 1:
        return " (+1 гость)"
    if guests in (2, 3, 4):
        return f" (+{guests} гостя)"
    return f" (+{guests} гостей)"


def _registration_privacy_note(data: dict) -> str:
    mode = data.get("registration_chat_name_mode")
    if not mode:
        return ""
    return (
        "\n\n🔐 В закрытом рабочем чате организаторы увидят полное имя, "
        "Telegram-ник и Telegram ID — это нужно для восстановления записи."
    )


async def _notify_registration_chat(
    admin_bot: Bot,
    show,
    attendee_name: str,
    guests: int,
    source: str | None,
    occupied_seats: int,
    telegram_user: User | None = None,
) -> None:
    if not getattr(show, "registration_chat_id", None):
        return
    party = 1 + guests
    source_line = f"\nИсточник: {h(source)}" if source else ""
    if telegram_user is None:
        telegram_lines = "\nTelegram: не указан\nTelegram ID: не указан"
    else:
        username = getattr(telegram_user, "username", None)
        username_line = (
            f'<a href="https://t.me/{h(username.lstrip("@"))}">@{h(username.lstrip("@"))}</a>'
            if username else "не указан"
        )
        telegram_lines = (
            f"\nTelegram: {username_line}"
            f"\nTelegram ID: <code>{telegram_user.telegram_id}</code>"
        )
    builder = InlineKeyboardBuilder()
    try:
        builder.button(
            text="➕ Добавить запись вручную",
            callback_data=AdminShowActionCb(
                action="chat_add_manual", show_id=show.id
            ).pack(),
        )
        await admin_bot.send_message(
            show.registration_chat_id,
            f"👤 <b>Новая запись</b>\n"
            f"🎭 {h(show.title)}\n"
            f"Полное имя: <b>{h(attendee_name)}</b>{telegram_lines}\n"
            f"Мест в записи: {party}\n"
            f"Заполнено: <b>{occupied_seats} / {show.max_seats}</b>{source_line}",
            reply_markup=builder.as_markup() if builder.buttons else None,
        )
    except Exception:
        logger.exception("failed to notify registration chat show_id=%s", show.id)
        creator = getattr(show, "creator", None)
        if creator is not None:
            try:
                await admin_bot.send_message(
                    creator.telegram_id,
                    f"⚠️ Не удалось отправить новую запись в чат шоу «{h(show.title)}». "
                    "Проверь, что бот остаётся администратором канала или группы и может публиковать сообщения.",
                )
            except Exception:
                logger.exception("failed to alert show creator about registration chat show_id=%s", show.id)


async def _notify_registration_cancellation(
    admin_bot: Bot,
    show,
    attendee_name: str,
    guests: int,
    occupied_seats: int,
) -> None:
    if not getattr(show, "registration_chat_id", None):
        return
    party = 1 + guests
    try:
        await admin_bot.send_message(
            show.registration_chat_id,
            f"↩️ <b>Запись отменена</b>\n"
            f"🎭 {h(show.title)}\n"
            f"Полное имя: <b>{h(attendee_name)}</b>\n"
            f"Освободилось мест: {party}\n"
            f"Заполнено: <b>{occupied_seats} / {show.max_seats}</b>",
        )
    except Exception:
        logger.exception("failed to notify registration chat about cancellation show_id=%s", show.id)
        creator = getattr(show, "creator", None)
        if creator is not None:
            try:
                await admin_bot.send_message(
                    creator.telegram_id,
                    f"⚠️ Не удалось отправить отмену записи в чат шоу «{h(show.title)}». "
                    "Проверь, что бот остаётся администратором канала или группы и может публиковать сообщения.",
                )
            except Exception:
                logger.exception("failed to alert show creator about cancellation chat show_id=%s", show.id)
