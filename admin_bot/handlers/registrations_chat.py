from __future__ import annotations

import csv
import io
from app_logging import get_project_logger
from aiogram import Router, F
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession
from db import crud
from db.base import AsyncSessionLocal
from db.models import UserRole
from config import settings
from admin_bot.keyboards.inline import checkin_counter_kb, checkin_kb, checkin_mode_kb, party_count_kb, registration_chat_kb, registrations_kb
from admin_bot.keyboards.reply import registration_channel_picker_kb, registrations_context_kb, show_context_kb
from admin_bot.callbacks import AdminCheckinCb, AdminManualCheckinCb, AdminPartyCountCb, AdminShowActionCb
from admin_bot.security import checkin_accessible_show, deny, manageable_show
from html_utils import h

logger = get_project_logger(__name__)
router = Router()

from admin_bot.handlers.registrations_entry import RegistrationChatFSM
from admin_bot.handlers.registrations_entry import _can_manage


async def _render_registrations(target, show_id: int, session: AsyncSession, edit: bool = True, is_super_admin: bool = False, db_user=None):
    show = await crud.get_show(session, show_id)
    regs = await crud.get_show_registrations(session, show_id)
    manual = await crud.get_manual_attendees(session, show_id)

    if show is None:
        return

    active = [r for r in regs if not r.is_cancelled]
    cancelled = [r for r in regs if r.is_cancelled]
    total = sum(1 + (r.guests or 0) for r in active) + len(manual)
    confirmed_count = sum(1 + (r.guests or 0) for r in active if r.confirmed is True)
    declined_count = sum(1 for r in active if r.confirmed is False)

    lines = [f"👥 <b>Записи на «{h(show.title)}»</b>", f"Всего: {total} / {show.max_seats}"]
    if confirmed_count or declined_count:
        lines.append(f"✅ Подтвердили: {confirmed_count}  ❌ Не придут: {declined_count}")
    lines.append("")

    n = 1
    for r in active:
        uname = f" (@{h(r.user.username)})" if r.user.username else ""
        guests = r.guests or 0
        guest_str = f" +{guests}" if guests > 0 else ""
        lines.append(f"{n}. {h(r.attendee_name)}{guest_str}{uname}")
        n += 1
    for att in manual:
        notify_status = "уведомлён(а)" if att.notification_confirmed_at else "уведомить вручную"
        lines.append(f"{n}. {h(att.name)} <i>[{notify_status}]</i>")
        n += 1
    if cancelled:
        lines.append(f"\n❌ Отменённых: {len(cancelled)}")

    text = "\n".join(lines)
    if len(text) > 4000:
        cut = text.rfind("\n", 0, 3990)
        text = text[:cut] + "\n..."

    kb = registrations_kb(show_id, manual, can_manage=_can_manage(is_super_admin, db_user, show.creator_id if show else None))
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
        except Exception:
            await target.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(AdminShowActionCb.filter(F.action == "regs"))
async def show_registrations(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    if await manageable_show(session, show_id, db_user, is_super_admin) is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await _render_registrations(callback.message, show_id, session, edit=True, is_super_admin=is_super_admin, db_user=db_user)
    await state.update_data(current_show_id=show_id, reply_context="registrations")
    await callback.message.answer("Действия с записями:", reply_markup=registrations_context_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "reg_chat"))
async def configure_registration_chat(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await state.set_state(RegistrationChatFSM.chat)
    await state.update_data(show_id=show.id)
    current = f"\n\nСейчас подключён: <b>{h(show.registration_chat_title or show.registration_chat_id)}</b>" if show.registration_chat_id else ""
    await callback.message.edit_text(
        "🔔 <b>Чат записей</b>\n\n"
        "Нажми <b>«Выбрать канал»</b> ниже. Telegram покажет каналы, которыми ты управляешь, "
        "сам добавит этого бота и запросит только право публикации сообщений.\n\n"
        "Никакой @username или числовой ID искать не нужно. После подключения бот отправит тестовое сообщение."
        f"{current}",
        reply_markup=registration_chat_kb(show.id, bool(show.registration_chat_id)),
    )
    await callback.message.answer(
        "Выбери канал системной кнопкой Telegram. Если канал не появляется, у тебя нет прав администратора в нём.",
        reply_markup=registration_channel_picker_kb(),
    )


async def _save_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, show, target, display_name: str) -> None:
    try:
        chat = await bot.get_chat(target)
        test = await bot.send_message(
            chat.id,
            f"✅ Чат подключён к шоу «{h(show.title)}». Здесь будут появляться новые записи.",
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "Не получилось написать в этот канал. Проверь, что бот добавлен с правом публикации."
        )
        return
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or display_name
    await crud.update_show(
        session, show.id, registration_chat_id=chat.id, registration_chat_title=title,
        registration_chat_name_mode="full",
    )
    await state.clear()
    await state.update_data(current_show_id=show.id, reply_context="registrations")
    await message.answer(f"✅ Чат записей подключён: <b>{h(title)}</b>.", reply_markup=registrations_context_kb())
    logger.info("registration chat configured show_id=%s chat_id=%s test_message_id=%s", show.id, chat.id, test.message_id)


@router.message(RegistrationChatFSM.chat, F.chat_shared)
async def save_shared_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, is_super_admin: bool = False, db_user=None):
    shared = message.chat_shared
    if shared.request_id != 7101:
        return
    show_id = (await state.get_data()).get("show_id")
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await state.clear()
        await message.answer("⛔ Нет доступа к этому шоу.")
        return
    try:
        shared_chat = await bot.get_chat(shared.chat_id)
        await crud.remember_registration_chat(session, db_user.id, shared_chat)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Не удалось получить выбранный канал. Попробуй выбрать его ещё раз.")
        return
    await _save_registration_chat(
        message, state, session, bot, show, shared.chat_id,
        shared.title or (f"@{shared.username}" if shared.username else str(shared.chat_id)),
    )


@router.message(RegistrationChatFSM.chat, F.text)
async def save_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, is_super_admin: bool = False, db_user=None):
    await message.answer("Выбери канал системной кнопкой Telegram — искать username или ID не нужно.", reply_markup=registration_channel_picker_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "reg_chat_clear"))
async def clear_registration_chat(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await crud.update_show(session, show.id, registration_chat_id=None, registration_chat_title=None)
    await state.clear()
    await callback.answer("Чат отключён")
    await callback.message.edit_text("🔕 Уведомления о новых записях для этого шоу отключены.")


@router.callback_query(AdminShowActionCb.filter(F.action == "manual_notified"))
async def confirm_manual_notifications(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    count = await crud.confirm_manual_attendees_notified(session, show.id)
    await callback.answer(f"Отмечено: {count}")
    await callback.message.edit_text(
        f"✅ <b>Зрители уведомлены вручную</b>\n\nШоу: «{h(show.title)}»\nОтмечено записей: {count}"
    )
