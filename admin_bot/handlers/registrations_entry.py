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



def _can_manage(is_super_admin: bool, db_user, show_creator_id: int | None = None) -> bool:
    if is_super_admin or (db_user is not None and db_user.role == UserRole.admin):
        return True
    if show_creator_id is not None and db_user is not None:
        return db_user.id == show_creator_id
    return False


@router.my_chat_member()
async def registration_chat_membership_updated(event: ChatMemberUpdated, bot) -> None:
    """Remember a chat when an organizer adds the admin bot and explain the next step."""
    active_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}
    if event.new_chat_member.status not in active_statuses or event.old_chat_member.status in active_statuses:
        return
    if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        return
    try:
        actor_member = await bot.get_chat_member(event.chat.id, event.from_user.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return
    if actor_member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return
    async with AsyncSessionLocal() as session:
        owner = await crud.get_user_by_telegram_id(session, event.from_user.id)
        if owner is None or owner.role not in {UserRole.organizer, UserRole.admin}:
            logger.info("registration chat not remembered: inviter has no organizer access telegram_id=%s chat_id=%s", event.from_user.id, event.chat.id)
            return
        await crud.remember_registration_chat(session, owner.id, event.chat)
    bot_url = f"https://t.me/{settings.ADMIN_BOT_USERNAME.lstrip('@')}?start=connected_chat"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть управление афишами", url=bot_url),
    ]])
    try:
        await bot.send_message(
            event.chat.id,
            "✅ <b>Чат подключён</b>\n\nТеперь его можно выбрать в поле «Чат записей» при создании или редактировании афиши.",
            reply_markup=keyboard,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.warning("connected registration chat saved but welcome could not be sent chat_id=%s", event.chat.id)


@router.message(Command("connect_chat"))
async def remember_current_registration_chat(message: Message, session: AsyncSession, bot, db_user=None):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Добавь меня в нужную группу и вызови там /connect_chat.")
        return
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Не удалось проверить твои права в этом чате.")
        return
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        await message.answer("Подключить чат может только его администратор.")
        return
    try:
        test = await bot.send_message(message.chat.id, "✅ Чат сохранён. Теперь его можно выбрать в Mini App в разделе «Чат записей».")
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Я не могу отправлять сообщения в этот чат. Проверь мои права.")
        return
    await crud.remember_registration_chat(session, db_user.id, message.chat)
    logger.info("registration chat remembered owner_user_id=%s chat_id=%s test_message_id=%s", db_user.id, message.chat.id, test.message_id)


def _csv_cell(value) -> str:
    """Prevent spreadsheet programs from evaluating exported user text as formulas."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class AddManualFSM(StatesGroup):
    chat_name = State()
    chat_source = State()
    chat_contact = State()
    chat_guests = State()


class DeleteManualFSM(StatesGroup):
    select = State()


class RegistrationChatFSM(StatesGroup):
    chat = State()


class CheckinSearchFSM(StatesGroup):
    query = State()


async def _current_show_from_state(state: FSMContext, session: AsyncSession, db_user, is_super_admin: bool):
    show_id = (await state.get_data()).get("current_show_id")
    return await manageable_show(session, show_id, db_user, is_super_admin) if show_id else None


@router.message(F.text == "🔔 Чат записей")
async def quick_registration_chat(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _current_show_from_state(state, session, db_user, is_super_admin)
    if show is None:
        await message.answer("Сначала открой шоу из афиши.", reply_markup=show_context_kb())
        return
    await state.set_state(RegistrationChatFSM.chat)
    await state.update_data(show_id=show.id, current_show_id=show.id)
    await message.answer(
        "🔔 <b>Чат записей</b>\n\nНажми «Выбрать канал». Telegram покажет каналы, "
        "которыми ты управляешь, добавит этого бота и запросит только право публикации. "
        "Искать @username или ID не нужно.",
        reply_markup=registration_channel_picker_kb(),
    )


@router.message(RegistrationChatFSM.chat, F.text == "⏭ Пропустить")
async def skip_registration_chat(message: Message, state: FSMContext):
    data = await state.get_data()
    show_id = data.get("show_id") or data.get("current_show_id")
    await state.clear()
    await state.update_data(current_show_id=show_id, reply_context="show")
    await message.answer("Чат записей пока не подключён. Это можно сделать позже в разделе «Записи».", reply_markup=show_context_kb())


@router.message(F.text == "🎟 Режим входа")
async def quick_checkin_mode(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _current_show_from_state(state, session, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await message.answer("Режим входа для этого шоу выключен.", reply_markup=registrations_context_kb())
        return
    await message.answer(
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n\nВыбери способ учёта:",
        reply_markup=checkin_mode_kb(show.id),
    )
