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

from admin_bot.handlers.registrations_entry import CheckinSearchFSM


async def _render_checkin(target, show_id: int, session: AsyncSession) -> None:
    show = await crud.get_show(session, show_id)
    if show is None or not show.checkin_enabled:
        await target.answer("Режим входа для этого шоу выключен.")
        return
    regs = await crud.get_show_registrations(session, show_id)
    manual = await crud.get_manual_attendees(session, show_id)
    active = [reg for reg in regs if not reg.is_cancelled]
    arrived = sum(reg.checked_in_count or 0 for reg in active) + sum(item.checked_in_count or 0 for item in manual)
    total = sum(1 + (reg.guests or 0) for reg in active) + len(manual)
    visible_regs = active[:50]
    visible_manual = manual[:max(0, 50 - len(visible_regs))]
    text = (
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n"
        f"Пришли: {arrived} / {total}\n\n"
        "Нажми на участника, чтобы изменить отметку."
    )
    if len(active) + len(manual) > 50:
        text += "\n\nПоказаны первые 50 записей. Для остальных используй поиск по имени."
    try:
        await target.edit_text(text, reply_markup=checkin_kb(show_id, visible_regs, visible_manual))
    except Exception:
        await target.answer(text, reply_markup=checkin_kb(show_id, visible_regs, visible_manual))


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_invite"))
async def create_checkin_staff_invite(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    session: AsyncSession,
    db_user=None,
    is_super_admin: bool = False,
):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    from config import settings
    invite = await crud.create_checkin_invite(session, show.id, settings.INVITE_TTL_HOURS)
    link = f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=door_{invite.token}"
    await callback.answer()
    await callback.message.answer(
        f"🚪 <b>Доступ сотруднику входа</b>\n\n"
        f"Отправь сотруднику одноразовую ссылку:\n<code>{link}</code>\n\n"
        f"Она действует {settings.INVITE_TTL_HOURS} ч. и выдаёт доступ только к отметке посетителей этого шоу. "
        "Редактирование шоу, списки и аналитика останутся закрыты.",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin"))
async def show_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await callback.message.edit_text(
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n\nВыбери способ учёта посетителей:",
        reply_markup=checkin_mode_kb(show.id),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_named"))
async def show_named_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    if show.checkin_mode == "counter" and (show.checkin_counter or 0) > 0:
        await callback.answer("Счётчик уже используется. Режим нельзя сменить во время входа.", show_alert=True)
        return
    await crud.update_show(session, show.id, checkin_mode="named")
    await callback.answer()
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_search"))
async def start_checkin_search(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    await callback.answer()
    await state.set_state(CheckinSearchFSM.query)
    await state.update_data(checkin_show_id=show.id)
    await callback.message.edit_text(
        "🔍 Введи имя, фамилию или Telegram username зрителя:",
    )


@router.message(CheckinSearchFSM.query, F.text)
async def find_checkin_attendee(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show_id = (await state.get_data()).get("checkin_show_id")
    show = await checkin_accessible_show(session, show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await state.clear()
        await message.answer("⛔ Режим входа недоступен.")
        return
    query = message.text.strip().lstrip("@").casefold()
    regs = [item for item in await crud.get_show_registrations(session, show.id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show.id)
    matches = []
    for item in regs:
        username = (item.user.username or "").casefold()
        if query in item.attendee_name.casefold() or query in username:
            matches.append(("r", item.id, item.attendee_name, item.checked_in_count or 0, 1 + (item.guests or 0)))
    for item in manual:
        if query in item.name.casefold():
            matches.append(("m", item.id, item.name, item.checked_in_count or 0, 1))
    builder = InlineKeyboardBuilder()
    for kind, item_id, name, actual, booked in matches[:20]:
        callback_data = (
            AdminCheckinCb(show_id=show.id, registration_id=item_id).pack()
            if kind == "r" else AdminManualCheckinCb(show_id=show.id, attendee_id=item_id).pack()
        )
        builder.button(text=f"{'✅' if actual else '⬜️'} {name} — {actual}/{booked}", callback_data=callback_data)
    builder.button(text="🔍 Искать снова", callback_data=AdminShowActionCb(action="checkin_search", show_id=show.id).pack())
    builder.button(text="📋 Весь список", callback_data=AdminShowActionCb(action="checkin_named", show_id=show.id).pack())
    builder.adjust(1)
    await state.clear()
    await message.answer(
        f"Найдено: {len(matches)}" if matches else "Никого не найдено.",
        reply_markup=builder.as_markup(),
    )


async def _notify_checkin_milestones(bot, session: AsyncSession, show, arrived: int) -> None:
    claim = await crud.claim_checkin_milestones(session, show.id, arrived)
    if claim is None:
        return
    previous, highest, chat_id, title = claim
    try:
        for milestone in range(previous + 10, highest + 1, 10):
            await bot.send_message(
                chat_id,
                f"🎟 На шоу «{h(title)}» пришли уже <b>{milestone}</b> человек.",
            )
    except Exception:
        await crud.release_checkin_milestones(session, show.id, highest, previous)
        logger.exception("failed to send check-in milestone show_id=%s", show.id)


async def _named_arrived_total(session: AsyncSession, show_id: int) -> int:
    regs = [item for item in await crud.get_show_registrations(session, show_id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show_id)
    return sum(item.checked_in_count or 0 for item in regs) + sum(item.checked_in_count or 0 for item in manual)


@router.callback_query(AdminCheckinCb.filter())
async def toggle_checkin(callback: CallbackQuery, callback_data: AdminCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    regs = await crud.get_show_registrations(session, show.id)
    reg = next((item for item in regs if item.id == callback_data.registration_id and not item.is_cancelled), None)
    if reg is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    booked = 1 + (reg.guests or 0)
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{h(reg.attendee_name)}</b>\nЗаписано: {booked}\nПришло: {reg.checked_in_count or 0}\n\nСколько человек пришло фактически?",
        reply_markup=party_count_kb(show.id, "r", reg.id, booked, reg.checked_in_count or 0),
    )


@router.callback_query(AdminManualCheckinCb.filter())
async def toggle_manual_checkin(callback: CallbackQuery, callback_data: AdminManualCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    manual = await crud.get_manual_attendees(session, show.id)
    attendee = next((item for item in manual if item.id == callback_data.attendee_id), None)
    if attendee is None:
        await callback.answer("Участник не найден", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{h(attendee.name)}</b>\nЗаписано: 1\nПришло: {attendee.checked_in_count or 0}\n\nСколько человек пришло фактически?",
        reply_markup=party_count_kb(show.id, "m", attendee.id, 1, attendee.checked_in_count or 0),
    )


@router.callback_query(AdminPartyCountCb.filter())
async def set_party_checkin(callback: CallbackQuery, callback_data: AdminPartyCountCb, session: AsyncSession, bot, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    if callback_data.kind == "r":
        item = await crud.set_registration_checkin_count(session, show.id, callback_data.item_id, callback_data.count)
    elif callback_data.kind == "m":
        item = await crud.set_manual_checkin_count(session, show.id, callback_data.item_id, callback_data.count)
    else:
        item = None
    if item is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    arrived = await _named_arrived_total(session, show.id)
    await _notify_checkin_milestones(bot, session, show, arrived)
    await callback.answer(f"Пришло: {callback_data.count}")
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminShowActionCb.filter(F.action.in_({"checkin_counter", "count_add1", "count_add5", "count_sub1"})))
async def counter_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, bot, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    delta = {"checkin_counter": 0, "count_add1": 1, "count_add5": 5, "count_sub1": -1}[callback_data.action]
    if show.checkin_mode != "counter":
        if await _named_arrived_total(session, show.id) > 0:
            await callback.answer("Учёт по именам уже начат. Режим нельзя сменить во время входа.", show_alert=True)
            return
        show = await crud.update_show(session, show.id, checkin_mode="counter")
    if delta:
        show = await crud.change_checkin_counter(session, show.id, delta)
    await _notify_checkin_milestones(bot, session, show, show.checkin_counter or 0)
    await callback.answer()
    await callback.message.edit_text(
        f"🔢 <b>Простой счётчик</b>\n\nФактически вошли: <b>{show.checkin_counter or 0}</b>",
        reply_markup=checkin_counter_kb(show.id),
    )
