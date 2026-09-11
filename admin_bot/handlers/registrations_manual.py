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
from admin_bot.telegram_usernames import normalize_telegram_username
from admin_bot.registration_notifications import notify_manual_registration
from html_utils import h

logger = get_project_logger(__name__)
router = Router()

from admin_bot.handlers.registrations_chat import _render_registrations
from admin_bot.handlers.registrations_entry import AddManualFSM
from admin_bot.handlers.registrations_entry import DeleteManualFSM
from admin_bot.handlers.registrations_entry import _can_manage


@router.callback_query(AdminShowActionCb.filter(F.action == "chat_add_manual"))
async def start_add_manual_from_registration_chat(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    state: FSMContext,
    session: AsyncSession,
    is_super_admin: bool = False,
    db_user=None,
):
    """Start manual entry from either the bot or the registration chat."""
    show = await crud.get_show(session, callback_data.show_id)
    if show is None or not _can_manage(is_super_admin, db_user, show.creator_id):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AddManualFSM.chat_name)
    await state.update_data(
        show_id=show.id,
        manual_source="social",
        current_show_id=show.id,
    )
    await callback.message.answer(
        f"➕ <b>Добавить запись на «{h(show.title)}»</b>\n\n"
        "Напиши имя одного зрителя ответом на это сообщение."
    )


@router.message(AddManualFSM.chat_name, F.text)
async def process_chat_manual_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("Имя должно содержать от 2 до 100 символов.")
        return
    await state.update_data(manual_name=name)
    await state.set_state(AddManualFSM.chat_source)
    builder = InlineKeyboardBuilder()
    builder.button(text="Telegram", callback_data="manual_source:telegram")
    builder.button(text="Instagram", callback_data="manual_source:instagram")
    builder.button(text="Другое", callback_data="manual_source:other")
    builder.adjust(2, 1)
    await message.answer("Откуда пришёл зритель и где с ним связаться?", reply_markup=builder.as_markup())


@router.callback_query(AddManualFSM.chat_source, F.data.startswith("manual_source:"))
async def process_chat_manual_source(callback: CallbackQuery, state: FSMContext):
    source = callback.data.split(":", 1)[1]
    if source not in {"telegram", "instagram", "other"}:
        await callback.answer("Неизвестный источник.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(manual_contact_source=source)
    await state.set_state(AddManualFSM.chat_contact)
    prompt = {
        "telegram": "Пришли Telegram-ник зрителя, например <code>@username</code>.",
        "instagram": "Пришли Instagram-ник зрителя, например <code>@username</code>.",
        "other": "Пришли телефон, ссылку или другой способ связи.",
    }[source]
    await callback.message.answer(prompt)


@router.message(AddManualFSM.chat_contact, F.text)
async def process_chat_manual_contact(message: Message, state: FSMContext):
    contact = message.text.strip()
    if len(contact) < 2 or len(contact) > 256:
        await message.answer("Контакт должен содержать от 2 до 256 символов.")
        return
    data = await state.get_data()
    source = data.get("manual_contact_source")
    telegram_username = None
    if source == "telegram":
        telegram_username = normalize_telegram_username(contact)
        if telegram_username is None:
            await message.answer("Неверный Telegram-ник. Пришли его в формате <code>@username</code>.")
            return
        contact = f"@{telegram_username}"
    elif source == "instagram":
        contact = "@" + contact.lstrip("@").strip()
    label = {"telegram": "Telegram", "instagram": "Instagram", "other": "Другое"}.get(source, "Контакт")
    await state.update_data(
        manual_contact=f"{label}: {contact}",
        manual_telegram_username=telegram_username,
    )
    await state.set_state(AddManualFSM.chat_guests)
    await message.answer("Сколько дополнительных гостей придёт с этим человеком? Отправь число от 0 до 50.")


@router.message(AddManualFSM.chat_guests, F.text)
async def process_chat_manual_guests(message: Message, state: FSMContext, session: AsyncSession, bot, is_super_admin: bool = False, db_user=None):
    try:
        guests = int(message.text.strip())
    except ValueError:
        guests = -1
    if guests < 0 or guests > 6:
        await message.answer("Отправь число дополнительных гостей от 0 до 6.")
        return
    data = await state.get_data()
    show_id = data["show_id"]
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await state.clear()
        await message.answer("⛔ Нет доступа к этому шоу.")
        return
    if guests > show.max_guests:
        await message.answer(f"Для этого шоу можно добавить не больше {show.max_guests} гостей.")
        return
    telegram_user = None
    telegram_username = data.get("manual_telegram_username")
    if telegram_username:
        telegram_user = await crud.get_user_by_username(session, telegram_username)

    if telegram_user is not None:
        registration = await crud.register_user_safe(
            session,
            show_id,
            telegram_user.id,
            data["manual_name"],
            guests,
            source="registration_chat",
        )
        count = int(registration is not None)
    else:
        count = await crud.add_manual_attendees(
            session,
            show_id,
            [data["manual_name"]],
            source=data.get("manual_contact_source", "social"),
            contacts=[data["manual_contact"]],
            guests=[guests],
        )
    await state.clear()
    await state.update_data(current_show_id=show_id, reply_context="show")
    if count == 0:
        occupied = await crud.count_active_registrations(session, show_id)
        await message.answer(f"😔 Не хватает мест: свободно {max(0, show.max_seats - occupied)}.", reply_markup=show_context_kb())
        return
    occupied = await crud.count_active_registrations(session, show_id)
    await notify_manual_registration(
        bot, show, name=data["manual_name"], contact=data["manual_contact"],
        guests=guests, occupied=occupied, automatic=telegram_user is not None,
    )
    reminder_note = (
        "\n🔔 Пользователь найден в боте и добавлен в автоматические напоминания."
        if telegram_user is not None else
        "\n🔔 За день попробую отправить напоминание автоматически; при ошибке сообщу в чате записей."
    )
    await message.answer(
        f"✅ Добавлен {h(data['manual_name'])}{f' +{guests}' if guests else ''}.\n"
        f"Связь: {h(data['manual_contact'])}{reminder_note}",
        reply_markup=show_context_kb(),
    )
    logger.info("added manual attendee from registration chat show_id=%s by admin=%s", show_id, message.from_user.id)


@router.callback_query(AdminShowActionCb.filter(F.action == "del_manual"))
async def delete_manual_start(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return
    await callback.answer()

    manual = await crud.get_manual_attendees(session, show_id)

    if not manual:
        await callback.message.answer("Нет участников, добавленных вручную.")
        return

    lines = ["🗑 <b>Удаление вручную добавленных</b>\n"]
    for i, att in enumerate(manual, start=1):
        lines.append(f"{i}. {h(att.name)}")
    lines.append("\nВведи номера для удаления через пробел или запятую (например: <code>1 3 5</code> или <code>2-8</code>):")

    await state.set_state(DeleteManualFSM.select)
    await state.update_data(show_id=show_id, manual_ids=[att.id for att in manual])
    await callback.message.answer("\n".join(lines))


@router.message(DeleteManualFSM.select, F.text)
async def delete_manual_process(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    show_id = data["show_id"]
    manual_ids: list[int] = data["manual_ids"]
    await state.clear()

    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(message, "⛔ Нет доступа к этому шоу.")
        return

    indices: set[int] = set()
    for part in message.text.replace(",", " ").split():
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                indices.update(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                indices.add(int(part))
            except ValueError:
                pass

    to_delete = [manual_ids[i - 1] for i in sorted(indices) if 1 <= i <= len(manual_ids)]
    if not to_delete:
        await message.answer("Ничего не выбрано или неверные номера.")
        await _render_registrations(message, show_id, session, edit=False, is_super_admin=is_super_admin, db_user=db_user)
        return

    for att_id in to_delete:
        await crud.delete_manual_attendee(session, att_id)
    logger.info("deleted %s manual attendees from show_id=%s by admin=%s", len(to_delete), show_id, message.from_user.id)
    await message.answer(f"✅ Удалено: {len(to_delete)} чел.")
    await _render_registrations(
        message, show_id, session, edit=False,
        is_super_admin=is_super_admin, db_user=db_user,
    )
