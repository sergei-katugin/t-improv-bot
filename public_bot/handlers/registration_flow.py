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
from public_bot.handlers.registration_entry import _notify_registration_chat
from public_bot.handlers.registration_entry import _registration_privacy_note


@router.callback_query(RegisterCb.filter())
async def start_registration(callback: CallbackQuery, callback_data: RegisterCb, state: FSMContext, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id

    show = await crud.get_show(session, show_id)
    if show is None or not show.is_active or show.show_date < utc_now() or (getattr(show, "registration_closes_at", None) and show.registration_closes_at <= utc_now()):
        await callback.answer()
        await callback.message.answer("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    existing = await crud.get_registration(session, show_id, db_user.id)

    if existing and not existing.is_cancelled:
        await callback.answer("Ты уже записан(а) на это шоу! 🎭", show_alert=True)
        return

    if active_count >= show.max_seats:
        builder = InlineKeyboardBuilder()
        builder.button(text="⏳ Встать в лист ожидания", callback_data=WaitlistCb(show_id=show_id).pack())
        await callback.answer()
        await callback.message.answer("Все места заняты, но можно встать в лист ожидания.", reply_markup=builder.as_markup())
        return

    await callback.answer()
    existing_state_data = await state.get_data()
    await state.set_state(RegisterFSM.enter_name)
    await state.update_data(
        show_id=show_id,
        show_title=show.title,
        show_date=format_local(show.show_date),
        registration_chat_name_mode=(show.registration_chat_name_mode if show.registration_chat_id else None),
        max_guests=getattr(show, "max_guests", 6),
        registration_source=(
            existing_state_data.get("registration_source")
            if existing_state_data.get("registration_source_show_id") == show_id
            else None
        ),
    )

    default_name = db_user.first_name or ""
    hint = " (или просто отправь своё имя)" if default_name else ""
    text = f"✏️ Введи своё имя для записи на шоу <b>{h(show.title)}</b>{hint}:"
    if callback.message.photo:
        await callback.message.answer(text)
    else:
        await callback.message.edit_text(text)


@router.message(RegisterFSM.enter_name, F.text)
async def process_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2 or len(name) > 100:
        await message.answer("Имя должно быть от 2 до 100 символов. Попробуй ещё раз:")
        return

    data = await state.get_data()
    show_id = data["show_id"]
    show_title = data["show_title"]
    show_date = data["show_date"]
    await state.update_data(attendee_name=name)

    if "guests" in data:
        # Name change — guests already chosen, skip to confirm
        guests = data["guests"]
        await state.set_state(RegisterFSM.confirm)
        label = _guests_label(guests)
        await message.answer(
            f"Записать тебя как <b>{h(name)}</b>{label}\n"
            f"на шоу <b>{h(show_title)}</b>\n"
            f"📅 {show_date}?{_registration_privacy_note(data)}",
            reply_markup=confirm_registration_kb(show_id),
        )
    else:
        await state.set_state(RegisterFSM.choose_guests)
        await message.answer(
            f"Сколько вас придёт на <b>{h(show_title)}</b>?",
            reply_markup=guests_kb(show_id, int(data.get("max_guests", 6))),
        )


@router.callback_query(RegisterFSM.choose_guests, GuestsCb.filter())
async def choose_guests(callback: CallbackQuery, callback_data: GuestsCb, state: FSMContext):
    show_id = callback_data.show_id
    guests = callback_data.guests
    if guests < 0 or guests > 6:
        await callback.answer("Некорректное количество гостей.", show_alert=True)
        return
    data = await state.get_data()
    max_guests = min(int(data.get("max_guests", 6)), 6)
    if guests < 0 or guests > max_guests:
        await callback.answer("Некорректное количество гостей.", show_alert=True)
        return
    if show_id != data.get("show_id"):
        await callback.answer("Эта кнопка устарела.", show_alert=True)
        return
    name = data["attendee_name"]
    show_title = data["show_title"]
    show_date = data["show_date"]

    await state.set_state(RegisterFSM.confirm)
    await state.update_data(guests=guests)
    await callback.answer()

    label = _guests_label(guests)
    await callback.message.edit_text(
        f"Записать тебя как <b>{h(name)}</b>{label}\n"
        f"на шоу <b>{h(show_title)}</b>\n"
        f"📅 {show_date}?{_registration_privacy_note(data)}",
        reply_markup=confirm_registration_kb(show_id),
    )


@router.callback_query(GuestsCustomCb.filter())
async def guests_custom(callback: CallbackQuery, callback_data: GuestsCustomCb, state: FSMContext, db_user: User):
    show_id = callback_data.show_id
    await callback.answer()
    current_state = await state.get_state()

    if current_state == RegisterFSM.choose_guests:
        await state.set_state(RegisterFSM.enter_guests_count)
        await callback.message.edit_text("Введи количество дополнительных гостей (только цифру):")
    else:
        await state.set_state(RegisterFSM.edit_guests_count)
        await state.update_data(edit_show_id=show_id)
        await callback.message.answer("Введи количество дополнительных гостей (только цифру):")


@router.message(RegisterFSM.enter_guests_count, F.text)
async def process_guests_count(message: Message, state: FSMContext):
    try:
        guests = int(message.text.strip())
        max_guests = min(int((await state.get_data()).get("max_guests", 6)), 6)
        if guests < 0 or guests > max_guests:
            raise ValueError
    except ValueError:
        await message.answer(f"Введи корректное число от 0 до {max_guests}:")
        return

    data = await state.get_data()
    show_id = data["show_id"]
    show_title = data["show_title"]
    show_date = data["show_date"]
    name = data["attendee_name"]

    await state.set_state(RegisterFSM.confirm)
    await state.update_data(guests=guests)

    label = _guests_label(guests)
    await message.answer(
        f"Записать тебя как <b>{h(name)}</b>{label}\n"
        f"на шоу <b>{h(show_title)}</b>\n"
        f"📅 {show_date}?{_registration_privacy_note(data)}",
        reply_markup=confirm_registration_kb(show_id),
    )


@router.message(RegisterFSM.edit_guests_count, F.text)
async def process_edit_guests_count(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    try:
        guests = int(message.text.strip())
        if guests < 0 or guests > 50:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное число от 0 до 50:")
        return

    data = await state.get_data()
    show_id = data.get("edit_show_id")
    await state.clear()
    if show_id is None:
        await message.answer("Что-то пошло не так. Попробуй заново через карточку шоу.")
        return

    show = await crud.get_show(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)
    if show is None or not show.is_active or show.show_date < utc_now() or reg is None or reg.is_cancelled:
        await message.answer("Ты не записан(а) на это шоу.")
        return
    updated = await crud.update_registration_guests_safe(session, show_id, db_user.id, guests)
    if updated is None:
        active_count = await crud.count_active_registrations(session, show_id)
        old_guests = reg.guests or 0
        await message.answer(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {show.max_seats - active_count + 1 + old_guests}."
        )
        return

    label = _guests_label(guests)
    await message.answer(f"✅ Обновлено: {1 + guests} чел.{label} на шоу <b>{h(show.title)}</b>.")


@router.callback_query(RegisterFSM.confirm, ConfirmRegCb.filter())
async def confirm_registration(callback: CallbackQuery, callback_data: ConfirmRegCb, state: FSMContext, db_user: User, session: AsyncSession, admin_bot: Bot):
    show_id = callback_data.show_id
    data = await state.get_data()
    if show_id != data.get("show_id") or "attendee_name" not in data:
        await callback.answer("Эта кнопка устарела.", show_alert=True)
        return
    attendee_name = data["attendee_name"]
    show_title = data.get("show_title", "")
    show_date = data.get("show_date", "")
    guests = data.get("guests", 0)
    source = data.get("registration_source")
    await state.clear()
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None or not show.is_active or show.show_date < utc_now():
        await callback.message.edit_text("Это шоу уже недоступно для записи.")
        return
    logger.info("user %s attempting registration for show_id=%s attendee=%s guests=%s", db_user.id, show_id, attendee_name, guests)
    reg = await crud.register_user_safe(
        session, show_id, db_user.id, attendee_name, guests=guests, source=source
    )
    if reg is None:
        active_count = await crud.count_active_registrations(session, show_id)
        await callback.message.edit_text(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {max(0, show.max_seats - active_count)}."
        )
        return

    label = _guests_label(guests)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    support = ""
    username = registrar_username(show)
    if username:
        support = (
            f'\n\n❓ По вопросам записи можно написать '
            f'<a href="https://t.me/{h(username)}">@{h(username)}</a>.'
        )
    privacy_note = (
        "Полное имя будет видно организаторам в закрытом рабочем канале."
        if show.registration_chat_id and show.registration_chat_name_mode == "full"
        else "Организаторы увидят имя в сокращённом виде."
        if show.registration_chat_id else ""
    )
    if privacy_note:
        privacy_note = f"\n\n🔐 {privacy_note}"
    await callback.message.answer(
        f"🎉 Ты записан(а) на шоу <b>{h(show_title)}</b>!\n\n"
        f"📅 {show_date}\n"
        f"Имя в записи: <b>{h(attendee_name)}</b>{label}\n\n"
        f"🔔 За день до шоу я пришлю напоминание. Дополнительные уведомления можно включить ниже.\n"
        f"📅 Здесь же можно добавить шоу в календарь."
        f"{privacy_note}"
        f"{support}",
        reply_markup=registration_success_kb(show, False, False, True),
    )
    occupied_seats = await crud.count_active_registrations(session, show_id)
    await _notify_registration_chat(
        admin_bot, show, attendee_name, guests, source, occupied_seats
    )
    logger.info("user %s registered id=%s show_id=%s attendee=%s guests=%s", db_user.id, reg.id, show_id, attendee_name, guests)
