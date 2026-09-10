from __future__ import annotations

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app_logging import get_project_logger
from db import crud
from html_utils import h
from telegram_delivery import send_with_retry

logger = get_project_logger(__name__)


_REPORTED_FIELDS = {
    0: "reminder_failure_reported_0d",
    1: "reminder_failure_reported_1d",
    2: "reminder_failure_reported_2d",
    7: "reminder_failure_reported_7d",
}


def needs_failure_report(registration, days: int) -> bool:
    return not bool(getattr(registration, _REPORTED_FIELDS[days], False))


def _person_line(registration) -> str:
    user = registration.user
    name = h(registration.attendee_name)
    username = getattr(user, "username", None)
    if username:
        return f'• {name} — <a href="https://t.me/{h(username.lstrip("@"))}">@{h(username.lstrip("@"))}</a>'
    return f'• <a href="tg://user?id={user.telegram_id}">{name}</a> — Telegram ID: <code>{user.telegram_id}</code>'


async def report_failed_personal_reminders(
    session, admin_bot: Bot, show, registrations: list, days: int
) -> None:
    if not registrations or not getattr(show, "registration_chat_id", None):
        return
    lines = "\n".join(_person_line(registration) for registration in registrations)
    if len(lines) > 3200:
        lines = lines[:3200].rsplit("\n", 1)[0] + "\n• …остальные — в списке зрителей"
    await session.commit()
    await send_with_retry(
        admin_bot.send_message,
        show.registration_chat_id,
        f"⚠️ <b>Не удалось отправить напоминание</b>\n\n"
        f"Бот не смог написать этим зрителям о шоу «{h(show.title)}»:\n\n{lines}\n\n"
        "Свяжись с ними вручную и попроси открыть бота, чтобы следующие сообщения доставлялись.",
    )
    await crud.mark_reminder_failures_reported(
        session, [registration.id for registration in registrations], days
    )


async def _maybe_remind_manual_attendees(session, admin_bot: Bot, show) -> None:
    """Ask the organizer to contact attendees whom the public bot cannot message."""
    if not getattr(show, "registration_chat_id", None):
        return
    attendees = await crud.get_pending_manual_attendees_for_reminder(
        session, show.id, limit=100
    )
    if not attendees:
        return
    await session.commit()
    names = "\n".join(
        f"• {h(item.name)}" + (f" — {h(item.contact)}" if item.contact else " — контакт не указан")
        for item in attendees
    )
    if len(names) > 3200:
        names = names[:3200].rsplit("\n", 1)[0] + "\n• …остальные — в списке зрителей"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✅ Уведомил(а) всех",
            callback_data=f"adm_s:manual_notified:{show.id}",
        )
    ]])
    try:
        await send_with_retry(
            admin_bot.send_message,
            show.registration_chat_id,
            f"📣 <b>Нужно уведомить вручную</b>\n\n"
            f"Завтра шоу «{h(show.title)}». Бот не может отправить этим зрителям "
            f"личное напоминание:\n\n{names}\n\n"
            "Свяжись с ними в той соцсети, где они записались, затем отметь задачу выполненной.",
            reply_markup=keyboard,
        )
        await crud.mark_manual_attendees_reminded(session, [item.id for item in attendees])
    except Exception:
        logger.exception("failed to remind organizer about manual attendees show_id=%s", show.id)
        creator = getattr(show, "creator", None)
        if creator is not None:
            try:
                await send_with_retry(
                    admin_bot.send_message,
                    creator.telegram_id,
                    f"⚠️ Не удалось отправить задачу в чат записей шоу «{h(show.title)}». "
                    "Проверь права бота в этом чате.",
                )
            except Exception:
                logger.exception("failed to alert creator about registration chat show_id=%s", show.id)
