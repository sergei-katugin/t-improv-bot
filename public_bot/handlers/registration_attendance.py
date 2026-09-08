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

from public_bot.handlers.registration_entry import RegisterFSM
from public_bot.handlers.registration_entry import _guests_label
from public_bot.handlers.registration_flow import choose_guests


@router.callback_query(RemindToggleCb.filter())
async def toggle_reminder(callback: CallbackQuery, callback_data: RemindToggleCb, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    field = callback_data.field
    new_val = bool(callback_data.value)

    valid_fields = {"remind_7d", "remind_2d", "remind_1d"}
    if field not in valid_fields:
        await callback.answer()
        return

    reg = await crud.set_reminder_pref(session, show_id, db_user.id, field, new_val)
    if reg is None:
        await callback.answer("Запись не найдена.")
        return

    await callback.answer()
    try:
        show = await crud.get_show(session, show_id)
        await callback.message.edit_reply_markup(
            reply_markup=registration_success_kb(
                show,
                remind_7d=reg.remind_7d,
                remind_2d=reg.remind_2d,
                remind_1d=reg.remind_1d,
            )
        )
    except Exception:
        pass


@router.callback_query(AttendanceCb.filter())
async def handle_attendance(callback: CallbackQuery, callback_data: AttendanceCb, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    action = callback_data.action

    reg = await crud.get_registration(session, show_id, db_user.id)
    if reg is None or reg.is_cancelled:
        await callback.answer("Запись не найдена.", show_alert=True)
        return

    await callback.answer()

    if action == "yes":
        await crud.set_confirmed(session, show_id, db_user.id, True)
        show = await crud.get_show(session, show_id)
        guests = reg.guests or 0
        total_str = f" (вас {1 + guests})" if guests > 0 else ""
        try:
            await callback.message.edit_text(
                f"✅ Отлично, ждём тебя{total_str} на шоу <b>{h(show.title)}</b>!\n\n"
                f"📅 {format_local(show.show_date)}"
            )
        except Exception:
            pass

    elif action == "no":
        await crud.set_confirmed(session, show_id, db_user.id, False)
        show = await crud.get_show(session, show_id)
        try:
            await callback.message.edit_text(
                f"😔 Жаль! Если передумаешь — восстанови запись через «📋 Мои записи».\n\n"
                f"Шоу: <b>{h(show.title)}</b>, {format_local(show.show_date)}"
            )
        except Exception:
            pass

    elif action == "guests":
        show = await crud.get_show(session, show_id)
        try:
            await callback.message.edit_text(
                f"Сколько вас придёт на <b>{h(show.title)}</b>?\n"
                f"Сейчас: {1 + (reg.guests or 0)} чел.",
                reply_markup=guests_kb(show_id, getattr(show, "max_guests", 6)),
            )
        except Exception:
            pass


@router.callback_query(EditGuestsCb.filter())
async def edit_guests_start(callback: CallbackQuery, callback_data: EditGuestsCb, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    reg = await crud.get_registration(session, show_id, db_user.id)
    show = await crud.get_show(session, show_id)

    if reg is None or reg.is_cancelled:
        await callback.message.answer("Запись не найдена.")
        return

    await callback.message.answer(
        f"Сколько вас придёт на <b>{h(show.title)}</b>?\n"
        f"Сейчас: {1 + reg.guests} чел.",
        reply_markup=guests_kb(show_id, getattr(show, "max_guests", 6)),
    )


@router.callback_query(GuestsCb.filter())
async def set_guests(callback: CallbackQuery, callback_data: GuestsCb, state: FSMContext, db_user: User, session: AsyncSession):
    current_state = await state.get_state()
    if current_state == RegisterFSM.choose_guests:
        await choose_guests(callback, callback_data, state)
        return

    show_id = callback_data.show_id
    guests = callback_data.guests
    show = await crud.get_show(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)
    if show is None or not show.is_active or show.show_date < utc_now() or (getattr(show, "registration_closes_at", None) and show.registration_closes_at <= utc_now()) or reg is None or reg.is_cancelled:
        await callback.message.edit_text("Ты не записан(а) на это шоу.")
        return
    max_guests = getattr(show, "max_guests", 6)
    if guests < 0 or guests > max_guests:
        await callback.answer(f"Можно добавить не больше {max_guests} гостей.", show_alert=True)
        return
    await callback.answer()
    updated = await crud.update_registration_guests_safe(session, show_id, db_user.id, guests)
    if updated is None:
        active_count = await crud.count_active_registrations(session, show_id)
        old_guests = reg.guests or 0
        await callback.message.edit_text(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {show.max_seats - active_count + 1 + old_guests}.",
            reply_markup=guests_kb(show_id, getattr(show, "max_guests", 6)),
        )
        return

    label = _guests_label(guests)
    await callback.message.edit_text(
        f"✅ Обновлено: {1 + guests} чел.{label} на шоу <b>{h(show.title)}</b>."
    )
