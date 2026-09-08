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

from admin_bot.handlers.registrations_entry import _csv_cell


@router.callback_query(AdminShowActionCb.filter(F.action == "analytics"))
async def show_analytics(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = await crud.get_show_registrations(session, show.id)
    manual = await crud.get_manual_attendees(session, show.id)
    feedback = await crud.get_show_feedback(session, show.id)
    active = [reg for reg in regs if not reg.is_cancelled]
    people = sum(1 + (reg.guests or 0) for reg in active) + len(manual)
    cancelled = len([reg for reg in regs if reg.is_cancelled])
    confirmed = sum(1 + (reg.guests or 0) for reg in active if reg.confirmed is True)
    arrived = (
        show.checkin_counter or 0
        if show.checkin_mode == "counter"
        else sum(reg.checked_in_count or 0 for reg in active) + sum(item.checked_in_count or 0 for item in manual)
    )
    sources: dict[str, int] = {}
    for reg in active:
        source = reg.source or "direct"
        sources[source] = sources.get(source, 0) + 1 + (reg.guests or 0)
    for attendee in manual:
        source = attendee.source or "manual"
        sources[source] = sources.get(source, 0) + 1
    source_labels = {"direct": "Через бота", "manual": "Вручную", "social": "Другие соцсети"}
    source_lines = "\n".join(
        f"• {h(source_labels.get(source, source))}: {count}"
        for source, count in sorted(sources.items(), key=lambda item: -item[1])
    )
    average = sum(item.rating for item in feedback) / len(feedback) if feedback else 0
    text = (
        f"📊 <b>Аналитика: {h(show.title)}</b>\n\n"
        f"👥 Записано людей: {people} / {show.max_seats}\n"
        f"↩️ Отмен регистраций: {cancelled}\n"
        f"✅ Подтвердили: {confirmed}\n"
        f"🎟 Пришли: {arrived if show.checkin_enabled else 'режим входа выключен'}\n"
        f"⭐ Средняя оценка: {average:.1f} ({len(feedback)} ответов)\n\n"
        f"<b>Источники:</b>\n{source_lines or 'Нет данных'}"
    )
    await callback.message.answer(text)


@router.callback_query(AdminShowActionCb.filter(F.action == "tasks"))
async def show_tasks(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = [item for item in await crud.get_show_registrations(session, show.id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show.id)
    pending_manual = sum(1 for item in manual if item.notification_confirmed_at is None)
    no_answer = sum(1 + (item.guests or 0) for item in regs if item.confirmed is None)
    occupied = sum(1 + (item.guests or 0) for item in regs) + len(manual)
    announced = await crud.has_any_announcement_been_sent(session, show.id)
    tasks = []
    if not announced:
        tasks.append("• 📣 Опубликовать анонс")
    if not show.registration_chat_id:
        tasks.append("• 🔔 Подключить рабочий канал записей")
    if pending_manual:
        tasks.append(f"• 💬 Уведомить вручную: {pending_manual}")
    if no_answer:
        tasks.append(f"• ❔ Не подтвердили участие: {no_answer}")
    if not tasks:
        tasks.append("• ✅ Срочных действий нет")
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Открыть записи", callback_data=AdminShowActionCb(action="regs", show_id=show.id).pack())
    if not show.registration_chat_id:
        builder.button(text="🔔 Подключить канал", callback_data=AdminShowActionCb(action="reg_chat", show_id=show.id).pack())
    if not announced:
        builder.button(text="📣 Продвижение", callback_data=AdminShowActionCb(action="promotion", show_id=show.id).pack())
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show.id).pack())
    builder.adjust(1)
    await callback.message.edit_text(
        f"🧭 <b>Задачи: {h(show.title)}</b>\n\n" + "\n".join(tasks) +
        f"\n\n🪑 Занято: {occupied} / {show.max_seats}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "export"))
async def export_show_csv(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = await crud.get_show_registrations(session, show.id)
    manual = await crud.get_manual_attendees(session, show.id)
    feedback_by_user = {item.user_id: item for item in await crud.get_show_feedback(session, show.id)}
    output = io.StringIO()
    # Semicolon opens into columns in Excel installations with a Russian locale.
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Имя", "Telegram", "Доп. гости", "Статус записи", "Подтверждение", "Пришло фактически",
        "Источник", "Оценка", "Отзыв",
    ])
    source_labels = {
        "direct": "Прямая ссылка",
        "instagram": "Instagram",
        "telegram": "Telegram",
        "channel": "Telegram-канал",
        "team": "Команда",
        "manual": "Добавлен вручную",
        "social": "Другие соцсети",
    }
    for reg in regs:
        item = feedback_by_user.get(reg.user_id)
        writer.writerow([
            _csv_cell(reg.attendee_name),
            _csv_cell(f"@{reg.user.username}" if reg.user.username else reg.user.telegram_id),
            reg.guests or 0,
            "Отменена" if reg.is_cancelled else "Активна",
            "Да" if reg.confirmed is True else "Нет" if reg.confirmed is False else "Не отвечал(а)",
            reg.checked_in_count or 0,
            _csv_cell(source_labels.get(reg.source or "direct", reg.source or "Прямая ссылка")),
            item.rating if item else "",
            _csv_cell(item.comment if item else ""),
        ])
    for attendee in manual:
        writer.writerow([
            _csv_cell(attendee.name), _csv_cell(attendee.contact or ""), 0, "Добавлен вручную", "Не требуется",
            attendee.checked_in_count or 0,
            _csv_cell(source_labels.get(attendee.source or "manual", attendee.source or "Добавлен вручную")), "", "",
        ])
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(data, filename=f"show-{show.id}-zriteli.csv"),
        caption=f"📥 Список зрителей по шоу «{h(show.title)}»",
    )
