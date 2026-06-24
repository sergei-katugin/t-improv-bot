from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import (
    confirm_registration_kb, show_detail_kb,
    reminder_prefs_kb, guests_kb,
)
from public_bot.keyboards.reply import main_menu_kb
from public_bot.callbacks import (
    RegisterCb, ConfirmRegCb, GuestsCb, GuestsCustomCb,
    RemindToggleCb, EditGuestsCb,
)

router = Router()


class RegisterFSM(StatesGroup):
    enter_name = State()
    choose_guests = State()
    enter_guests_count = State()
    confirm = State()
    edit_guests_count = State()


def _guests_label(guests: int) -> str:
    if guests == 0:
        return ""
    if guests == 1:
        return " (+1 гость)"
    if guests in (2, 3, 4):
        return f" (+{guests} гостя)"
    return f" (+{guests} гостей)"


@router.callback_query(RegisterCb.filter())
async def start_registration(callback: CallbackQuery, callback_data: RegisterCb, state: FSMContext, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.answer()
        await callback.message.answer("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    existing = await crud.get_registration(session, show_id, db_user.id)

    if existing and not existing.is_cancelled:
        await callback.answer("Ты уже записан(а) на это шоу! 🎭", show_alert=True)
        return

    if active_count >= show.max_seats:
        await callback.answer("😔 К сожалению, все места уже заняты.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(RegisterFSM.enter_name)
    await state.update_data(
        show_id=show_id,
        show_title=show.title,
        show_date=show.show_date.strftime("%d.%m.%Y %H:%M"),
    )

    default_name = db_user.first_name or ""
    hint = " (или просто отправь своё имя)" if default_name else ""
    text = f"✏️ Введи своё имя для записи на шоу <b>{show.title}</b>{hint}:"
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
            f"Записать тебя как <b>{name}</b>{label}\n"
            f"на шоу <b>{show_title}</b>\n"
            f"📅 {show_date}?",
            reply_markup=confirm_registration_kb(show_id),
        )
    else:
        await state.set_state(RegisterFSM.choose_guests)
        await message.answer(
            f"Сколько вас придёт на <b>{show_title}</b>?",
            reply_markup=guests_kb(show_id),
        )


@router.callback_query(RegisterFSM.choose_guests, GuestsCb.filter())
async def choose_guests(callback: CallbackQuery, callback_data: GuestsCb, state: FSMContext):
    show_id = callback_data.show_id
    guests = callback_data.guests

    data = await state.get_data()
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
        f"Записать тебя как <b>{name}</b>{label}\n"
        f"на шоу <b>{show_title}</b>\n"
        f"📅 {show_date}?",
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
        if guests < 0 or guests > 50:
            raise ValueError
    except ValueError:
        await message.answer("Введи корректное число от 0 до 50:")
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
        f"Записать тебя как <b>{name}</b>{label}\n"
        f"на шоу <b>{show_title}</b>\n"
        f"📅 {show_date}?",
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
    active_count = await crud.count_active_registrations(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)
    if reg is None or reg.is_cancelled:
        await message.answer("Ты не записан(а) на это шоу.")
        return
    old_guests = reg.guests
    seats_after = active_count - (1 + old_guests) + (1 + guests)
    if seats_after > show.max_seats:
        await message.answer(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {show.max_seats - active_count + 1 + old_guests}."
        )
        return
    await crud.update_registration_guests(session, show_id, db_user.id, guests)

    label = _guests_label(guests)
    await message.answer(f"✅ Обновлено: {1 + guests} чел.{label} на шоу <b>{show.title}</b>.")


@router.callback_query(RegisterFSM.confirm, ConfirmRegCb.filter())
async def confirm_registration(callback: CallbackQuery, callback_data: ConfirmRegCb, state: FSMContext, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    data = await state.get_data()
    attendee_name = data["attendee_name"]
    show_title = data.get("show_title", "")
    show_date = data.get("show_date", "")
    guests = data.get("guests", 0)
    await state.clear()
    await callback.answer()

    show = await crud.get_show(session, show_id)
    reg = await crud.register_user_safe(
        session, show_id, db_user.id, attendee_name, guests=guests, max_seats=show.max_seats
    )
    if reg is None:
        active_count = await crud.count_active_registrations(session, show_id)
        await callback.message.edit_text(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {max(0, show.max_seats - active_count)}."
        )
        return

    upcoming = await crud.list_upcoming_shows(session)
    updated_menu = main_menu_kb(has_shows=bool(upcoming), has_regs=True)

    label = _guests_label(guests)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        f"🎉 Ты записан(а) на шоу <b>{show_title}</b>!\n\n"
        f"📅 {show_date}\n"
        f"Имя в записи: <b>{attendee_name}</b>{label}\n\n"
        f"За день до шоу я пришлю напоминание. Увидимся! 🎭",
        reply_markup=updated_menu,
    )


    await callback.message.answer(
        "🔔 <b>Когда тебя уведомить о шоу?</b>\n"
        "Нажми ещё раз, чтобы отключить.",
        reply_markup=reminder_prefs_kb(show_id, remind_14d=False, remind_7d=False, remind_1d=True),
    )


@router.callback_query(RemindToggleCb.filter())
async def toggle_reminder(callback: CallbackQuery, callback_data: RemindToggleCb, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    field = callback_data.field
    new_val = bool(callback_data.value)

    valid_fields = {"remind_14d", "remind_7d", "remind_1d"}
    if field not in valid_fields:
        await callback.answer()
        return

    reg = await crud.set_reminder_pref(session, show_id, db_user.id, field, new_val)
    if reg is None:
        await callback.answer("Запись не найдена.")
        return
    r14, r7, r1 = reg.remind_14d, reg.remind_7d, reg.remind_1d

    await callback.answer()
    try:
        await callback.message.edit_reply_markup(
            reply_markup=reminder_prefs_kb(show_id, remind_14d=r14, remind_7d=r7, remind_1d=r1)
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
        f"Сколько вас придёт на <b>{show.title}</b>?\n"
        f"Сейчас: {1 + reg.guests} чел.",
        reply_markup=guests_kb(show_id),
    )


@router.callback_query(GuestsCb.filter())
async def set_guests(callback: CallbackQuery, callback_data: GuestsCb, state: FSMContext, db_user: User, session: AsyncSession):
    current_state = await state.get_state()
    if current_state == RegisterFSM.choose_guests:
        await choose_guests(callback, callback_data, state)
        return

    show_id = callback_data.show_id
    guests = callback_data.guests
    await callback.answer()

    show = await crud.get_show(session, show_id)
    active_count = await crud.count_active_registrations(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)
    if reg is None or reg.is_cancelled:
        await callback.message.edit_text("Ты не записан(а) на это шоу.")
        return
    old_guests = reg.guests
    seats_after = active_count - (1 + old_guests) + (1 + guests)
    if seats_after > show.max_seats:
        await callback.message.edit_text(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {show.max_seats - active_count + 1 + old_guests}.",
            reply_markup=guests_kb(show_id),
        )
        return
    await crud.update_registration_guests(session, show_id, db_user.id, guests)

    label = _guests_label(guests)
    await callback.message.edit_text(
        f"✅ Обновлено: {1 + guests} чел.{label} на шоу <b>{show.title}</b>."
    )
