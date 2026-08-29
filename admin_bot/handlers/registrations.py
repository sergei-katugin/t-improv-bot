from __future__ import annotations

from app_logging import get_project_logger

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import UserRole
from admin_bot.keyboards.inline import registrations_kb
from admin_bot.callbacks import AdminShowActionCb


def _can_manage(is_super_admin: bool, db_user, show_creator_id: int | None = None) -> bool:
    if is_super_admin or (db_user is not None and db_user.role == UserRole.admin):
        return True
    if show_creator_id is not None and db_user is not None:
        return db_user.id == show_creator_id
    return False

logger = get_project_logger(__name__)
router = Router()


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

    lines = [f"👥 <b>Записи на «{show.title}»</b>", f"Всего: {total} / {show.max_seats}"]
    if confirmed_count or declined_count:
        lines.append(f"✅ Подтвердили: {confirmed_count}  ❌ Не придут: {declined_count}")
    lines.append("")

    n = 1
    for r in active:
        uname = f" (@{r.user.username})" if r.user.username else ""
        guests = r.guests or 0
        guest_str = f" +{guests}" if guests > 0 else ""
        lines.append(f"{n}. {r.attendee_name}{guest_str}{uname}")
        n += 1
    for att in manual:
        lines.append(f"{n}. {att.name} <i>[вручную]</i>")
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
    await callback.answer()
    await _render_registrations(callback.message, show_id, session, edit=True, is_super_admin=is_super_admin, db_user=db_user)


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
        lines.append(f"{i}. {att.name}")
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
    await _render_registrations(message, show_id, session, edit=False)
