from __future__ import annotations

import asyncio
from app_logging import get_project_logger
from datetime import datetime, time, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from sqlalchemy import func, select
from public_bot.keyboards.inline import attendance_kb, feedback_kb, reminder_cancel_kb

from config import settings
from db.base import AsyncSessionLocal, engine, is_sqlite
from db import crud
from html_utils import h
from telegram_delivery import send_with_retry
from time_utils import format_local, local_date, local_naive_to_utc, local_now
from scheduler.setup import configure_scheduler

logger = get_project_logger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.APP_TIMEZONE)



def setup_scheduler(public_bot: Bot, admin_bot: Bot) -> None:
    configure_scheduler(
        scheduler, public_bot, admin_bot,
        announcement_job=check_and_send_announcements,
        feedback_job=request_post_show_feedback,
        chat_cleanup_job=disconnect_finished_registration_chats,
        fsm_cleanup_job=cleanup_stale_fsm,
    )
    logger.info("Scheduler started")








async def request_post_show_feedback(public_bot: Bot) -> None:
    """Ask attendees for feedback shortly after a show, once per registration."""
    if is_sqlite:
        await _run_post_show_feedback(public_bot)
        return

    lock_id = 0x54494D504642
    async with engine.connect() as lock_connection:
        acquired = bool((await lock_connection.execute(
            select(func.pg_try_advisory_lock(lock_id))
        )).scalar())
        if not acquired:
            logger.info("Skipping feedback requests: another replica holds the scheduler lock")
            return
        try:
            await _run_post_show_feedback(public_bot)
        finally:
            await lock_connection.execute(select(func.pg_advisory_unlock(lock_id)))


async def _run_post_show_feedback(public_bot: Bot) -> None:
    after_id = 0
    while True:
        async with AsyncSessionLocal() as session:
            regs = await crud.get_feedback_candidates(session, after_id=after_id, limit=50)
            if not regs:
                return
            after_id = regs[-1].id
            candidates = [
                (reg.id, reg.user.telegram_id, reg.show_id, reg.show.title)
                for reg in regs
            ]

        sent_ids: list[int] = []
        for start in range(0, len(candidates), 5):
            batch = candidates[start:start + 5]

            async def send_one(candidate) -> int | None:
                registration_id, telegram_id, show_id, show_title = candidate
                try:
                    await send_with_retry(
                        public_bot.send_message,
                        telegram_id,
                        f"🎭 Как тебе шоу <b>{h(show_title)}</b>? Оцени одним нажатием:",
                        reply_markup=feedback_kb(show_id),
                    )
                    return registration_id
                except Exception:
                    logger.warning("Could not request feedback registration_id=%s", registration_id)
                    return None

            results = await asyncio.gather(*(send_one(candidate) for candidate in batch))
            sent_ids.extend(reg_id for reg_id in results if reg_id is not None)

        async with AsyncSessionLocal() as session:
            await crud.mark_feedback_requested(session, sent_ids)








async def check_and_send_announcements(public_bot: Bot, admin_bot: Bot) -> None:
    if is_sqlite:
        await _run_announcement_check(public_bot, admin_bot)
        return

    lock_id = 0x54494D50524F
    async with engine.connect() as lock_connection:
        acquired = bool((await lock_connection.execute(
            select(func.pg_try_advisory_lock(lock_id))
        )).scalar())
        if not acquired:
            logger.info("Skipping announcement check: another replica holds the scheduler lock")
            return
        try:
            await _run_announcement_check(public_bot, admin_bot)
        finally:
            await lock_connection.execute(select(func.pg_advisory_unlock(lock_id)))


async def _run_announcement_check(public_bot: Bot, admin_bot: Bot) -> None:
    now = local_now()
    if now.hour < settings.REMINDER_HOUR_LOCAL:
        logger.info(
            "Skipping reminder reconciliation before configured hour %02d:00",
            settings.REMINDER_HOUR_LOCAL,
        )
        return
    today = now.date()
    logger.info("Running daily announcement check for %s", today)
    async with AsyncSessionLocal() as session:
        reminder_window_end = local_naive_to_utc(
            datetime.combine(today + timedelta(days=8), time.min)
        )
        shows = await crud.list_upcoming_shows(session, before=reminder_window_end)
    for show in shows:
        async with AsyncSessionLocal() as session:
            days_left = (local_date(show.show_date) - today).days
            if days_left == 7:
                await _maybe_send_channel(session, public_bot, admin_bot, show, "7d")
                await _maybe_send_personal(session, public_bot, show, 7)
            elif days_left == 2:
                await _maybe_send_channel(session, public_bot, admin_bot, show, "2d")
                await _maybe_send_personal(session, public_bot, show, 2)
            elif days_left == 1:
                await _maybe_send_channel(session, public_bot, admin_bot, show, "1d")
                await _maybe_send_personal(session, public_bot, show, 1)
                await _maybe_remind_manual_attendees(session, admin_bot, show)
            elif days_left == 0:
                await _maybe_send_channel(session, public_bot, admin_bot, show, "0d")
                await _maybe_send_personal(session, public_bot, show, 0)


async def _maybe_send_channel(session, public_bot: Bot, admin_bot: Bot, show, ann_type: str) -> None:
    if await crud.has_announcement_been_sent(session, show.id, ann_type):
        return
    await session.commit()
    text = build_announcement_text(show, ann_type)
    try:
        msg_id = await send_to_channel(public_bot, admin_bot, show, text)
        await crud.mark_announcement_sent(session, show.id, ann_type, channel_message_id=msg_id)
        logger.info("Sent %s announcement for show %s (msg_id=%s)", ann_type, show.id, msg_id)
    except Exception:
        logger.exception("Failed to send channel announcement for show %s", show.id)


async def _maybe_send_personal(session, bot: Bot, show, days: int) -> None:
    intros = {
        7: "🔔 До шоу осталась неделя!",
        2: "🔔 До шоу осталось два дня!",
        1: "🔔 Завтра твоё шоу!",
    }
    date_str = format_local(show.show_date)
    location_line = _location_line(show)

    channel_msg_id = await crud.get_last_channel_message_id(session, show.id)
    await session.commit()
    post_url = None
    if channel_msg_id:
        from config import settings
        ch = settings.ANNOUNCEMENT_CHANNEL_ID
        if ch.startswith("@"):
            post_url = f"https://t.me/{ch.lstrip('@')}/{channel_msg_id}"
        else:
            post_url = f"https://t.me/c/{str(ch).replace('-100', '').lstrip('-')}/{channel_msg_id}"

    async def send_one(reg) -> int | None:
        try:
            if days == 0:
                text = (
                    f"🎭 <b>Сегодня твоё шоу!</b>\n\n"
                    f"Ты записан(а) на <b>{h(show.title)}</b>\n"
                    f"📅 {date_str}\n{location_line}\n\n"
                    f"Подтверди своё участие — мы сообщим организаторам, кто придёт:"
                )
                kb = attendance_kb(show.id)
                await send_with_retry(bot.send_message, reg.user.telegram_id, text, reply_markup=kb)
            else:
                intro = intros[days]
                text = f"{intro}\n\nТы записан(а) на шоу <b>{h(show.title)}</b>\n📅 {date_str}\n{location_line}"
                kwargs = {}
                if days == 1:
                    text += "\n\nЕсли планы изменились, отмени запись кнопкой ниже — место освободится для другого зрителя."
                    kwargs["reply_markup"] = reminder_cancel_kb(show.id)
                if post_url:
                    kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
                await send_with_retry(bot.send_message, reg.user.telegram_id, text, **kwargs)
            return reg.id
        except Exception as e:
            logger.warning("Failed to send %dd reminder to user %s: %s", days, reg.user.telegram_id, e)
            return None

    sent = 0
    after_id = 0
    query_batch_size = 50
    send_batch_size = 5
    while True:
        regs = await crud.get_registrations_for_reminder(
            session,
            show.id,
            days,
            after_id=after_id,
            limit=query_batch_size,
        )
        if not regs:
            break
        after_id = regs[-1].id
        # Release the DB connection while Telegram sends are in flight.
        await session.commit()
        sent_ids: list[int] = []
        for start in range(0, len(regs), send_batch_size):
            batch = regs[start:start + send_batch_size]
            results = await asyncio.gather(*(send_one(reg) for reg in batch))
            sent_ids.extend(reg_id for reg_id in results if reg_id is not None)
        await crud.mark_reminded_many(session, sent_ids, days)
        sent += len(sent_ids)
    logger.info("Sent %dd personal reminders for show %s to %s users", days, show.id, sent)


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
            f"Завтра шоу «{h(show.title)}». Бот не может написать этим зрителям, "
            f"потому что они добавлены не через Telegram:\n\n{names}\n\n"
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


from scheduler.messages import DATE_RE, MAPS_RE, TIME_RE, _fmt_date, _location_line
from scheduler.messages import _register_button, _registrar_line, build_announcement_text, build_personal_reminder

from scheduler.delivery import _download_photo, cache_poster_for_public_bot, _send_to_channel_once, send_to_channel
from scheduler.cleanup import cleanup_stale_fsm, disconnect_finished_registration_chats, _run_registration_chat_cleanup
