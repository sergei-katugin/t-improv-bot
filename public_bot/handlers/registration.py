from app_logging import get_project_logger
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import (
    confirm_registration_kb, show_detail_kb,
    reminder_prefs_kb, guests_kb, attendance_kb, calendar_kb,
)
from public_bot.keyboards.reply import main_menu_kb
from public_bot.callbacks import (
    RegisterCb, ConfirmRegCb, GuestsCb, GuestsCustomCb,
    RemindToggleCb, EditGuestsCb, AttendanceCb, CalendarCb, FeedbackCb,
)
from html_utils import h
from time_utils import format_local, utc_now

router = Router()

import logging
logger = get_project_logger(__name__)


class RegisterFSM(StatesGroup):
    enter_name = State()
    choose_guests = State()
    enter_guests_count = State()
    confirm = State()
    edit_guests_count = State()
    feedback_comment = State()


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
    if show is None or not show.is_active or show.show_date < utc_now():
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
    existing_state_data = await state.get_data()
    await state.set_state(RegisterFSM.enter_name)
    await state.update_data(
        show_id=show_id,
        show_title=show.title,
        show_date=format_local(show.show_date),
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
            f"📅 {show_date}?",
            reply_markup=confirm_registration_kb(show_id),
        )
    else:
        await state.set_state(RegisterFSM.choose_guests)
        await message.answer(
            f"Сколько вас придёт на <b>{h(show_title)}</b>?",
            reply_markup=guests_kb(show_id),
        )


@router.callback_query(RegisterFSM.choose_guests, GuestsCb.filter())
async def choose_guests(callback: CallbackQuery, callback_data: GuestsCb, state: FSMContext):
    show_id = callback_data.show_id
    guests = callback_data.guests
    if guests < 0 or guests > 50:
        await callback.answer("Некорректное количество гостей.", show_alert=True)
        return

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
        f"Записать тебя как <b>{h(name)}</b>{label}\n"
        f"на шоу <b>{h(show_title)}</b>\n"
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
        f"Записать тебя как <b>{h(name)}</b>{label}\n"
        f"на шоу <b>{h(show_title)}</b>\n"
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
async def confirm_registration(callback: CallbackQuery, callback_data: ConfirmRegCb, state: FSMContext, db_user: User, session: AsyncSession):
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

    upcoming = await crud.list_upcoming_shows(session)
    updated_menu = main_menu_kb(has_shows=bool(upcoming), has_regs=True)

    label = _guests_label(guests)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer(
        f"🎉 Ты записан(а) на шоу <b>{h(show_title)}</b>!\n\n"
        f"📅 {show_date}\n"
        f"Имя в записи: <b>{h(attendee_name)}</b>{label}\n\n"
        f"За день до шоу я пришлю напоминание. Увидимся! 🎭",
        reply_markup=updated_menu,
    )
    await callback.message.answer("Добавить шоу в календарь:", reply_markup=calendar_kb(show))
    logger.info("user %s registered id=%s show_id=%s attendee=%s guests=%s", db_user.id, reg.id, show_id, attendee_name, guests)


    await callback.message.answer(
        "🔔 <b>Напоминания</b>\n"
        "В день шоу я напишу тебе автоматически. "
        "Выбери дополнительные уведомления (нажми ещё раз, чтобы отключить):",
        reply_markup=reminder_prefs_kb(show_id, remind_7d=False, remind_2d=False, remind_1d=True),
    )


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@router.callback_query(CalendarCb.filter())
async def download_calendar_event(callback: CallbackQuery, callback_data: CalendarCb, session: AsyncSession):
    show = await crud.get_show(session, callback_data.show_id)
    if show is None:
        await callback.answer("Шоу не найдено.", show_alert=True)
        return
    await callback.answer()
    from datetime import timedelta

    end = show.show_date + timedelta(hours=2)
    description = _ics_escape(show.poster_text or "Импровизационное шоу")
    location = _ics_escape(f"{show.location}, {show.city}")
    content = (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//T Impro Bot//RU\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:show-{show.id}@t-impro-bot\r\n"
        f"DTSTART:{show.show_date.strftime('%Y%m%dT%H%M%S')}Z\r\n"
        f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}Z\r\n"
        f"SUMMARY:{_ics_escape(show.title)}\r\n"
        f"LOCATION:{location}\r\nDESCRIPTION:{description}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    await callback.message.answer_document(
        BufferedInputFile(content.encode("utf-8"), filename=f"show-{show.id}.ics"),
        caption="📅 Файл события для Apple Calendar и Outlook",
    )


@router.callback_query(FeedbackCb.filter())
async def submit_feedback_rating(
    callback: CallbackQuery,
    callback_data: FeedbackCb,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
):
    if callback_data.rating not in range(1, 6):
        await callback.answer("Некорректная оценка.", show_alert=True)
        return
    reg = await crud.get_registration(session, callback_data.show_id, db_user.id)
    if reg is None or reg.is_cancelled:
        await callback.answer("Запись на шоу не найдена.", show_alert=True)
        return
    await crud.save_feedback(session, callback_data.show_id, db_user.id, callback_data.rating)
    await state.set_state(RegisterFSM.feedback_comment)
    await state.update_data(feedback_show_id=callback_data.show_id, feedback_rating=callback_data.rating)
    await callback.answer("Спасибо!")
    await callback.message.edit_text(
        f"Спасибо за оценку {callback_data.rating} ⭐\n\n"
        "Если хочешь, напиши короткий комментарий. Чтобы пропустить, отправь /skip."
    )


@router.message(RegisterFSM.feedback_comment, F.text)
async def submit_feedback_comment(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    data = await state.get_data()
    await state.clear()
    if message.text.strip() == "/skip":
        await message.answer("Спасибо за обратную связь! 🎭")
        return
    comment = message.text.strip()
    if len(comment) > 1000:
        comment = comment[:1000]
    await crud.save_feedback(
        session,
        data["feedback_show_id"],
        db_user.id,
        data["feedback_rating"],
        comment,
    )
    await message.answer("Спасибо! Комментарий сохранён 🎭")


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
        await callback.message.edit_reply_markup(
            reply_markup=reminder_prefs_kb(
                show_id,
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
                reply_markup=guests_kb(show_id),
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
    if guests < 0 or guests > 50:
        await callback.answer("Некорректное количество гостей.", show_alert=True)
        return
    await callback.answer()

    show = await crud.get_show(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)
    if show is None or not show.is_active or show.show_date < utc_now() or reg is None or reg.is_cancelled:
        await callback.message.edit_text("Ты не записан(а) на это шоу.")
        return
    updated = await crud.update_registration_guests_safe(session, show_id, db_user.id, guests)
    if updated is None:
        active_count = await crud.count_active_registrations(session, show_id)
        old_guests = reg.guests or 0
        await callback.message.edit_text(
            f"😔 Мест не хватает: нужно {1 + guests}, осталось {show.max_seats - active_count + 1 + old_guests}.",
            reply_markup=guests_kb(show_id),
        )
        return

    label = _guests_label(guests)
    await callback.message.edit_text(
        f"✅ Обновлено: {1 + guests} чел.{label} на шоу <b>{h(show.title)}</b>."
    )
