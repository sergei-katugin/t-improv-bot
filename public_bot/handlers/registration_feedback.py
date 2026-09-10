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
from public_bot.keyboards.inline import confirm_registration_kb, show_detail_kb, registration_success_kb, guests_kb, attendance_kb, calendar_kb, registrar_username, optional_feedback_comment_kb, cancel_feedback_comment_kb
from public_bot.callbacks import RegisterCb, ConfirmRegCb, GuestsCb, GuestsCustomCb, RemindToggleCb, EditGuestsCb, AttendanceCb, CalendarCb, FeedbackCb, FeedbackCommentCb, WaitlistCb
from html_utils import h
from time_utils import format_local, utc_now

router = Router()
logger = get_project_logger(__name__)

from public_bot.handlers.registration_entry import RegisterFSM


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
    if not await crud.can_submit_feedback(session, callback_data.show_id, db_user.id):
        await callback.answer("Сейчас оставить отзыв для этого шоу нельзя.", show_alert=True)
        return
    await crud.save_feedback(session, callback_data.show_id, db_user.id, callback_data.rating)
    await state.clear()
    await callback.answer("Спасибо!")
    await callback.message.edit_text(
        f"Спасибо за оценку {callback_data.rating} ⭐\n\n"
        "Оценка сохранена — на этом всё.",
        reply_markup=optional_feedback_comment_kb(
            callback_data.show_id, callback_data.rating,
        ),
    )


@router.callback_query(FeedbackCommentCb.filter(F.action == "add"))
async def start_feedback_comment(
    callback: CallbackQuery,
    callback_data: FeedbackCommentCb,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
):
    if callback_data.rating not in range(1, 6) or not await crud.can_submit_feedback(
        session, callback_data.show_id, db_user.id,
    ):
        await callback.answer("Сейчас добавить комментарий нельзя.", show_alert=True)
        return
    await state.set_state(RegisterFSM.feedback_comment)
    await state.update_data(
        feedback_show_id=callback_data.show_id,
        feedback_rating=callback_data.rating,
    )
    await callback.answer()
    await callback.message.edit_text(
        "Комментарий необязателен. Если хочешь дополнить оценку, отправь его одним сообщением.",
        reply_markup=cancel_feedback_comment_kb(
            callback_data.show_id, callback_data.rating,
        ),
    )


@router.callback_query(FeedbackCommentCb.filter(F.action == "cancel"))
async def cancel_feedback_comment(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text("Спасибо! Оценка сохранена ⭐")


@router.message(RegisterFSM.feedback_comment, F.text)
async def submit_feedback_comment(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    data = await state.get_data()
    await state.clear()
    show_id = data.get("feedback_show_id")
    rating = data.get("feedback_rating")
    if not isinstance(show_id, int) or rating not in range(1, 6):
        await message.answer("Запрос на отзыв устарел. Открой афишу заново.")
        return
    if not await crud.can_submit_feedback(session, show_id, db_user.id):
        await message.answer("Сейчас оставить отзыв для этого шоу нельзя.")
        return
    comment = message.text.strip()
    if len(comment) > 1000:
        comment = comment[:1000]
    await crud.save_feedback(
        session,
        show_id,
        db_user.id,
        rating,
        comment,
    )
    await message.answer("Спасибо! Комментарий сохранён 🎭")
