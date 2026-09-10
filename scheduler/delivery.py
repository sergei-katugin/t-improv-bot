from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app_logging import get_project_logger
from config import settings
from scheduler.messages import _register_button

logger = get_project_logger(__name__)


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


async def _send_to_channel_once(
    public_bot: Bot, admin_bot: Bot, show, text: str,
    kb, reply_to_message_id: int | None,
) -> int:
    logger.info("_send_to_channel_once start show_id=%s reply_to=%s", getattr(show, 'id', None), reply_to_message_id)
    kwargs = {"reply_to_message_id": reply_to_message_id} if reply_to_message_id else {}
    if show.poster_file_id:
        try:
            async with _download_photo(admin_bot, show.poster_file_id) as photo:
                if len(text) <= 1024:
                    msg = await public_bot.send_photo(
                        settings.ANNOUNCEMENT_CHANNEL_ID, photo=photo, caption=text, reply_markup=kb, **kwargs
                    )
                    return msg.message_id
                await public_bot.send_photo(settings.ANNOUNCEMENT_CHANNEL_ID, photo=photo, **kwargs)
            msg = await public_bot.send_message(
                settings.ANNOUNCEMENT_CHANNEL_ID, text, reply_markup=kb, **kwargs
            )
            return msg.message_id
        except Exception:
            logger.warning("Could not download poster for show %s, sending text only", show.id)
    msg = await public_bot.send_message(
        settings.ANNOUNCEMENT_CHANNEL_ID, text, reply_markup=kb, **kwargs,
    )
    logger.info(
        "_send_to_channel_once sent text for show_id=%s msg_id=%s",
        getattr(show, "id", None), msg.message_id,
    )
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
