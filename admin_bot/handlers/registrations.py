from __future__ import annotations

import csv
import io

from app_logging import get_project_logger

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import UserRole
from admin_bot.keyboards.inline import checkin_kb, registrations_kb
from admin_bot.callbacks import AdminCheckinCb, AdminManualCheckinCb, AdminShowActionCb
from admin_bot.security import deny, manageable_show
from html_utils import h


def _can_manage(is_super_admin: bool, db_user, show_creator_id: int | None = None) -> bool:
    if is_super_admin or (db_user is not None and db_user.role == UserRole.admin):
        return True
    if show_creator_id is not None and db_user is not None:
        return db_user.id == show_creator_id
    return False

logger = get_project_logger(__name__)
router = Router()


def _csv_cell(value) -> str:
    """Prevent spreadsheet programs from evaluating exported user text as formulas."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class AddManualFSM(StatesGroup):
    names = State()


class DeleteManualFSM(StatesGroup):
    select = State()


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
        lines.append(f"{n}. {h(att.name)} <i>[вручную]</i>")
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
async def show_registrations(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    if await manageable_show(session, show_id, db_user, is_super_admin) is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await _render_registrations(callback.message, show_id, session, edit=True, is_super_admin=is_super_admin, db_user=db_user)


async def _render_checkin(target, show_id: int, session: AsyncSession) -> None:
    show = await crud.get_show(session, show_id)
    if show is None or not show.checkin_enabled:
        await target.answer("Check-in для этого шоу выключен.")
        return
    regs = await crud.get_show_registrations(session, show_id)
    manual = await crud.get_manual_attendees(session, show_id)
    active = [reg for reg in regs if not reg.is_cancelled]
    arrived = sum(1 + (reg.guests or 0) for reg in active if reg.checked_in_at) + sum(1 for item in manual if item.checked_in_at)
    total = sum(1 + (reg.guests or 0) for reg in active) + len(manual)
    text = (
        f"🎟 <b>Check-in: {h(show.title)}</b>\n"
        f"Пришли: {arrived} / {total}\n\n"
        "Нажми на участника, чтобы изменить отметку."
    )
    try:
        await target.edit_text(text, reply_markup=checkin_kb(show_id, active, manual))
    except Exception:
        await target.answer(text, reply_markup=checkin_kb(show_id, active, manual))


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin"))
async def show_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminCheckinCb.filter())
async def toggle_checkin(callback: CallbackQuery, callback_data: AdminCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Check-in недоступен.")
        return
    reg = await crud.toggle_registration_checkin(session, show.id, callback_data.registration_id)
    await callback.answer("Отметка изменена" if reg else "Запись не найдена")
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminManualCheckinCb.filter())
async def toggle_manual_checkin(callback: CallbackQuery, callback_data: AdminManualCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Check-in недоступен.")
        return
    attendee = await crud.toggle_manual_attendee_checkin(session, show.id, callback_data.attendee_id)
    await callback.answer("Отметка изменена" if attendee else "Участник не найден")
    await _render_checkin(callback.message, show.id, session)


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
    arrived = sum(1 + (reg.guests or 0) for reg in active if reg.checked_in_at) + sum(1 for item in manual if item.checked_in_at)
    sources: dict[str, int] = {}
    for reg in active:
        source = reg.source or "direct"
        sources[source] = sources.get(source, 0) + 1 + (reg.guests or 0)
    source_lines = "\n".join(f"• {h(source)}: {count}" for source, count in sorted(sources.items(), key=lambda item: -item[1]))
    average = sum(item.rating for item in feedback) / len(feedback) if feedback else 0
    text = (
        f"📊 <b>Аналитика: {h(show.title)}</b>\n\n"
        f"👥 Записано людей: {people} / {show.max_seats}\n"
        f"↩️ Отмен регистраций: {cancelled}\n"
        f"✅ Подтвердили: {confirmed}\n"
        f"🎟 Пришли: {arrived if show.checkin_enabled else 'check-in выключен'}\n"
        f"⭐ Средняя оценка: {average:.1f} ({len(feedback)} ответов)\n\n"
        f"<b>Источники:</b>\n{source_lines or 'Нет данных'}"
    )
    await callback.message.answer(text)


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
    writer = csv.writer(output)
    writer.writerow([
        "name", "telegram", "guests", "status", "confirmed", "checked_in",
        "source", "rating", "feedback",
    ])
    for reg in regs:
        item = feedback_by_user.get(reg.user_id)
        writer.writerow([
            _csv_cell(reg.attendee_name),
            _csv_cell(f"@{reg.user.username}" if reg.user.username else reg.user.telegram_id),
            reg.guests or 0,
            "cancelled" if reg.is_cancelled else "active",
            reg.confirmed,
            bool(reg.checked_in_at),
            _csv_cell(reg.source or "direct"),
            item.rating if item else "",
            _csv_cell(item.comment if item else ""),
        ])
    for attendee in manual:
        writer.writerow([
            _csv_cell(attendee.name), "", 0, "manual", "", bool(attendee.checked_in_at),
            "manual", "", "",
        ])
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(data, filename=f"show-{show.id}-registrations.csv"),
        caption=f"📤 Выгрузка по шоу «{h(show.title)}»",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "add_manual"))
async def start_add_manual(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AddManualFSM.names)
    await state.update_data(show_id=show_id)
    await callback.message.edit_text(
        "➕ <b>Добавить участников вручную</b>\n\n"
        "Отправь список имён — каждое имя с новой строки:\n\n"
        "<i>Иван Иванов\nМария Петрова\nАлексей Сидоров</i>"
    )


@router.message(AddManualFSM.names, F.text)
async def process_manual_names(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    show_id = data["show_id"]
    await state.clear()
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await message.answer("⛔ Нет доступа к этому шоу.")
        return

    names = [n.strip() for n in message.text.splitlines() if n.strip()]
    if not names:
        await message.answer("Список пустой, попробуй ещё раз.")
        return

    count = await crud.add_manual_attendees(session, show_id, names)
    if count == 0:
        occupied = await crud.count_active_registrations(session, show_id)
        await message.answer(
            f"😔 Нельзя добавить {len(names)}: свободно {max(0, show.max_seats - occupied)} мест."
        )
        return
    await message.answer(f"✅ Добавлено: {count} чел.")
    logger.info("added %s manual attendees to show_id=%s by admin=%s", count, show_id, message.from_user.id)
    await _render_registrations(message, show_id, session, edit=False, is_super_admin=is_super_admin, db_user=db_user)


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
