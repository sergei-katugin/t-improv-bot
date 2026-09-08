from __future__ import annotations

from aiogram import Bot
from sqlalchemy import func, select

from app_logging import get_project_logger
from config import settings
from db import crud
from db.base import AsyncSessionLocal, engine, is_sqlite
from html_utils import h
from telegram_delivery import send_with_retry

logger = get_project_logger(__name__)


async def cleanup_stale_fsm() -> None:
    from db.fsm_storage import SQLAlchemyStorage

    deleted = await SQLAlchemyStorage.cleanup_stale(settings.FSM_TTL_DAYS)
    if deleted:
        logger.info("Deleted %d stale FSM storage records", deleted)


async def disconnect_finished_registration_chats(admin_bot: Bot) -> None:
    """Notify and detach working chats two hours after a show starts."""
    if is_sqlite:
        await _run_registration_chat_cleanup(admin_bot)
        return
    lock_id = 0x54494D504348
    async with engine.connect() as lock_connection:
        acquired = bool((await lock_connection.execute(
            select(func.pg_try_advisory_lock(lock_id))
        )).scalar())
        if not acquired:
            return
        try:
            await _run_registration_chat_cleanup(admin_bot)
        finally:
            await lock_connection.execute(select(func.pg_advisory_unlock(lock_id)))


async def _run_registration_chat_cleanup(admin_bot: Bot) -> None:
    async with AsyncSessionLocal() as session:
        shows = await crud.list_finished_shows_with_registration_chat(session)
        outcomes = await crud.get_show_outcomes(session, [show.id for show in shows])
        targets = [(show, outcomes[show.id]) for show in shows]
    for show, outcome in targets:
        show_id, title, chat_id, capacity = show.id, show.title, show.registration_chat_id, show.max_seats
        registered, arrived, cancelled = outcome["registered"], outcome["arrived"], outcome["cancelled"]
        feedback_count, average_rating = outcome["feedback_count"], outcome["average_rating"]
        try:
            await send_with_retry(
                admin_bot.send_message,
                chat_id,
                f"📊 <b>Итоги шоу «{h(title)}»</b>\n\n"
                f"Записались: <b>{registered} / {capacity}</b>\n"
                f"Пришли: <b>{arrived}</b>\n"
                f"Отменили запись: <b>{cancelled}</b>\n"
                f"Отзывы: <b>{feedback_count}</b>"
                f"{f' · ★ {average_rating:.1f}' if feedback_count else ''}\n\n"
                "Чат автоматически отключён от завершённого шоу.",
            )
        except Exception:
            logger.exception("failed to send registration chat summary show_id=%s", show_id)
            continue
        async with AsyncSessionLocal() as session:
            if await crud.mark_registration_chat_summary_sent(session, show_id, chat_id) and await crud.clear_registration_chat_if_matches(session, show_id, chat_id):
                logger.info("automatically disconnected registration chat show_id=%s chat_id=%s", show_id, chat_id)
