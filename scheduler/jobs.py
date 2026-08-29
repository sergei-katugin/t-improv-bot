from __future__ import annotations

import asyncio
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from app_logging import get_project_logger
from datetime import datetime, date, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
from sqlalchemy import func, select
from public_bot.keyboards.inline import attendance_kb, feedback_kb

from config import settings
from db.base import AsyncSessionLocal, engine, is_sqlite
from db import crud
from html_utils import h
from time_utils import format_local, local_date, local_now, utc_to_local

logger = get_project_logger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.APP_TIMEZONE)

DAYS_MAP = {
    "7d": 7,
    "2d": 2,
    "1d": 1,
    "0d": 0,
}


@asynccontextmanager
async def _download_photo(bot: Bot, file_id: str):
    """Download a Telegram file to disk so it is not duplicated in process memory."""
    temporary = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    temporary_path = Path(temporary.name)
    temporary.close()
    try:
        file = await bot.get_file(file_id)
        await bot.download_file(file.file_path, destination=temporary_path)
        yield FSInputFile(temporary_path, filename="poster.jpg")
    finally:
        temporary_path.unlink(missing_ok=True)


def setup_scheduler(public_bot: Bot, admin_bot: Bot) -> None:
    scheduler.add_job(
        check_and_send_announcements,
        CronTrigger(
            hour=settings.REMINDER_HOUR_LOCAL,
            minute=0,
            timezone=settings.APP_TIMEZONE,
        ),
        args=[public_bot, admin_bot],
        id="daily_announcement_check",
        replace_existing=True,
    )
    scheduler.add_job(
        request_post_show_feedback,
        IntervalTrigger(hours=1),
        args=[public_bot],
        id="post_show_feedback",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started")


async def request_post_show_feedback(public_bot: Bot) -> None:
    """Ask attendees for feedback shortly after a show, once per registration."""
    after_id = 0
    while True:
        async with AsyncSessionLocal() as session:
            regs = await crud.get_feedback_candidates(session, after_id=after_id, limit=50)
            if not regs:
                return
            after_id = regs[-1].id
            sent_ids: list[int] = []
            for start in range(0, len(regs), 5):
                batch = regs[start:start + 5]

                async def send_one(reg) -> int | None:
                    try:
                        await public_bot.send_message(
                            reg.user.telegram_id,
                            f"🎭 Как тебе шоу <b>{h(reg.show.title)}</b>? Оцени одним нажатием:",
                            reply_markup=feedback_kb(reg.show_id),
                        )
                        return reg.id
                    except Exception:
                        logger.warning("Could not request feedback registration_id=%s", reg.id)
                        return None

                results = await asyncio.gather(*(send_one(reg) for reg in batch))
                sent_ids.extend(reg_id for reg_id in results if reg_id is not None)
            await crud.mark_feedback_requested(session, sent_ids)


async def cache_poster_for_public_bot(
    admin_bot: Bot, public_bot: Bot, poster_file_id: str, target_chat_id: int
) -> str | None:
    """Download poster via admin_bot, re-upload via public_bot to get a public-bot file_id.
    Uses the main admin's chat and immediately deletes the message so it's invisible."""
    from config import ADMIN_ID_LIST
    cache_chat = ADMIN_ID_LIST[0] if ADMIN_ID_LIST else target_chat_id
    try:
        async with _download_photo(admin_bot, poster_file_id) as photo:
            msg = await public_bot.send_photo(cache_chat, photo=photo)
        pub_file_id = msg.photo[-1].file_id
        try:
            await public_bot.delete_message(cache_chat, msg.message_id)
        except Exception:
            pass
        return pub_file_id
    except Exception:
        logger.warning("Could not cache poster for public bot (file_id=%s)", poster_file_id)
        return None


def _register_button(show) -> InlineKeyboardMarkup | None:
    if show is None or not show.id:
        return None
    url = f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show.id}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Записаться на шоу", url=url)
    ]])


async def _send_to_channel_once(
    public_bot: Bot, admin_bot: Bot, show, text: str,
    kb, reply_to_message_id: int | None,
) -> int:
    logger.info("_send_to_channel_once start show_id=%s reply_to=%s", getattr(show, 'id', None), reply_to_message_id)
    kwargs = {"reply_to_message_id": reply_to_message_id} if reply_to_message_id else {}
    if show.poster_file_id:
        try:
            async with _download_photo(admin_bot, show.poster_file_id) as photo:
                msg = await public_bot.send_photo(
                    settings.ANNOUNCEMENT_CHANNEL_ID, photo=photo, caption=text, reply_markup=kb, **kwargs
                )
            return msg.message_id
        except Exception:
            logger.warning("Could not download poster for show %s, sending text only", show.id)
        msg = await public_bot.send_message(settings.ANNOUNCEMENT_CHANNEL_ID, text, reply_markup=kb, **kwargs)
        logger.info("_send_to_channel_once sent text for show_id=%s msg_id=%s", getattr(show, 'id', None), msg.message_id)
        return msg.message_id


async def send_to_channel(
    public_bot: Bot, admin_bot: Bot, show, text: str,
    with_button: bool = True, reply_to_message_id: int | None = None,
) -> int | None:
    """Send announcement to channel via public_bot. Returns channel message_id."""
    from aiogram.exceptions import TelegramBadRequest
    kb = _register_button(show) if with_button else None
    logger.info("send_to_channel attempting show_id=%s with_button=%s reply_to=%s", getattr(show, 'id', None), with_button, reply_to_message_id)
    try:
        return await _send_to_channel_once(public_bot, admin_bot, show, text, kb, reply_to_message_id)
    except TelegramBadRequest as e:
        if reply_to_message_id and "message to be replied not found" in str(e):
            logger.warning("Reply message not found for show %s, sending without reply", show.id)
            return await _send_to_channel_once(public_bot, admin_bot, show, text, kb, None)
        raise


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
    today = local_now().date()
    logger.info("Running daily announcement check for %s", today)
    async with AsyncSessionLocal() as session:
        shows = await crud.list_upcoming_shows(session)
        for show in shows:
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
            elif days_left == 0:
                await _maybe_send_channel(session, public_bot, admin_bot, show, "0d")
                await _maybe_send_personal(session, public_bot, show, 0)


async def _maybe_send_channel(session, public_bot: Bot, admin_bot: Bot, show, ann_type: str) -> None:
    if await crud.has_announcement_been_sent(session, show.id, ann_type):
        return
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
                await bot.send_message(reg.user.telegram_id, text, reply_markup=kb)
            else:
                intro = intros[days]
                text = f"{intro}\n\nТы записан(а) на шоу <b>{h(show.title)}</b>\n📅 {date_str}\n{location_line}"
                kwargs = {}
                if post_url:
                    kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
                await bot.send_message(reg.user.telegram_id, text, **kwargs)
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
        sent_ids: list[int] = []
        for start in range(0, len(regs), send_batch_size):
            batch = regs[start:start + send_batch_size]
            results = await asyncio.gather(*(send_one(reg) for reg in batch))
            sent_ids.extend(reg_id for reg_id in results if reg_id is not None)
        await crud.mark_reminded_many(session, sent_ids, days)
        sent += len(sent_ids)
    logger.info("Sent %dd personal reminders for show %s to %s users", days, show.id, sent)


MAPS_RE = re.compile(r'(maps\.google|goo\.gl/maps|maps\.app\.goo\.gl|google\.com/maps)', re.I)
DATE_RE = re.compile(r'\d{1,2}[./-]\d{1,2}[./-]\d{2,4}')
TIME_RE = re.compile(r'\b\d{1,2}:\d{2}\b')


_MONTHS_GEN = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
_WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]


def _fmt_date(dt) -> str:
    dt = utc_to_local(dt)
    return f"{dt.day} {_MONTHS_GEN[dt.month]}, {_WEEKDAYS_RU[dt.weekday()]}, {dt.strftime('%H:%M')}"


def _location_line(show, plain: bool = False) -> str:
    if show.location_url and not plain:
        return f'📍 <a href="{h(show.location_url)}">{h(show.location)}</a>, {h(show.city)}'
    return f"📍 {h(show.location)}, {h(show.city)}"


def _registrar_line(show) -> str | None:
    bot_username = settings.PUBLIC_BOT_USERNAME.lstrip("@")
    bot_link = f'<a href="https://t.me/{bot_username}">@{h(bot_username)}</a>'
    registrar = getattr(show, "registrar", None)
    username = getattr(show, "registrar_username", None) or (registrar.username if registrar else None)
    if username:
        username = username.lstrip("@")
        person_link = f'<a href="https://t.me/{username}">@{h(username)}</a>'
        return f"👥 Записаться тут: {bot_link} и {person_link}"
    return f"👥 Записаться тут: {bot_link}"


_ANN_HEADERS = {
    "7d": "🎭 Через неделю:",
    "2d": "🎭 Через два дня:",
    "1d": "🎭 Завтра:",
    "0d": "🎭 Сегодня!",
}

_REGISTER_NOTE = "👆 Нажми кнопку — и твоё место сразу запомнится!"


def build_announcement_text(
    show,
    ann_type: str | None = None,
    *,
    seats_left: int | None = None,
    attendee_line: str | None = None,
    include_registration: bool = True,
) -> str:
    if ann_type is None:
        header = f"🎭 <b>{h(show.title)}</b>"
    else:
        prefix = _ANN_HEADERS.get(ann_type, "🎭")
        header = f"{prefix} <b>{h(show.title)}</b>"

    poster = show.poster_text or ""
    poster_has_date = bool(DATE_RE.search(poster))
    poster_has_maps = bool(MAPS_RE.search(poster))

    lines = [header]
    if getattr(show, "team_name", None):
        lines.append(f"👥 Команда: {h(show.team_name)}")
    if not poster_has_date:
        lines.append(f"📅 {_fmt_date(show.show_date)}")
    lines.append(_location_line(show, plain=poster_has_maps))
    if seats_left is not None:
        lines.append(f"🪑 Свободных мест: {seats_left}/{show.max_seats}")
    if include_registration:
        registrar_line = _registrar_line(show)
        if registrar_line:
            lines.append(registrar_line)
    if attendee_line:
        lines.append(attendee_line)

    if poster:
        lines.append("")
        lines.append(h(poster))

    if ann_type is not None:
        lines.append("")
        lines.append(_REGISTER_NOTE)

    return "\n".join(lines)


def build_personal_reminder(
    show, custom_intro: str | None = None
) -> tuple[str, InlineKeyboardMarkup | None]:
    intro = custom_intro or "👋 Напоминание! Завтра шоу, на которое ты записан(а):"
    lines = [intro, "", build_announcement_text(show)]
    text = "\n".join(lines)
    kb = _register_button(show)
    return text, kb
