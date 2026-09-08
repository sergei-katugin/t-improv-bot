from __future__ import annotations
from admin_bot.handlers.shows_shared import *

async def _notify_show_change(show, field: str, old_value, admin_bot: Bot, public_bot: Bot):
    if field == "show_date":
        await _notify_date_change(show, old_value, admin_bot, public_bot)
        return

    labels = {
        "title": ("название", "🎭"),
        "location": ("площадка", "📍"),
        "city": ("город", "🏙"),
    }
    label, icon = labels[field]
    new_value = getattr(show, field)
    if new_value == old_value:
        return
    old_text = h(str(old_value))
    new_text = h(str(new_value))
    async with AsyncSessionLocal() as session:
        reply_to = await crud.get_last_channel_message_id(session, show.id)
        users = await crud.get_registered_users_for_show(session, show.id)

    channel_text = (
        f"⚠️ <b>Изменилось {label} шоу</b>\n\n"
        f"{icon} Было: <s>{old_text}</s>\n"
        f"{icon} Стало: <b>{new_text}</b>\n\n"
        "Обновлённый анонс:"
    )
    try:
        await send_to_channel(public_bot, admin_bot, show, channel_text, reply_to_message_id=reply_to)
    except Exception:
        logger.exception("Failed to post show change field=%s show=%s", field, show.id)

    personal_text = (
        f"⚠️ <b>В шоу изменилось {label}</b>\n\n"
        f"{icon} Было: <s>{old_text}</s>\n"
        f"{icon} Стало: <b>{new_text}</b>\n\n"
        f"🎭 {h(show.title)}\n📅 {format_local(show.show_date)}\n{_location_line(show)}"
    )
    from public_bot.keyboards.inline import manage_registration_kb
    sent, failed = 0, 0
    for user in users:
        try:
            await send_with_retry(
                public_bot.send_message,
                user.telegram_id, personal_text, reply_markup=manage_registration_kb(show.id),
            )
            sent += 1
        except Exception:
            failed += 1
    logger.info("Show-change notifications field=%s sent=%s failed=%s show=%s", field, sent, failed, show.id)


async def _notify_date_change(show, old_date, admin_bot: Bot, public_bot: Bot):
    from db import crud as _crud
    old_str = format_local(old_date)
    new_str = format_local(show.show_date)

    async with AsyncSessionLocal() as session:
        reply_to = await _crud.get_last_channel_message_id(session, show.id)

    channel_text = (
        f"⚠️ <b>Изменение даты!</b>\n\n"
        f"📅 Было: <s>{old_str}</s>\n"
        f"📅 Стало: {new_str}\n\n"
        f"Обновлённый анонс:"
    )
    try:
        await send_to_channel(
            public_bot, admin_bot, show, channel_text,
            reply_to_message_id=reply_to,
        )
    except Exception:
        logger.exception("Failed to post date-change to channel")

    new_date_str = format_local(show.show_date)
    location_line = _location_line(show)
    personal_text = (
        f"⚠️ <b>Дата шоу изменилась!</b>\n\n"
        f"Ты записан(а) на шоу <b>{h(show.title)}</b>\n"
        f"📅 Было: <s>{old_str}</s>\n"
        f"📅 Стало: {new_date_str}\n"
        f"{location_line}"
    )

    async with AsyncSessionLocal() as session:
        users = await crud.get_registered_users_for_show(session, show.id)
        channel_msg_id = await crud.get_last_channel_message_id(session, show.id)

    post_url = None
    if channel_msg_id:
        ch = settings.ANNOUNCEMENT_CHANNEL_ID
        if ch.startswith("@"):
            post_url = f"https://t.me/{ch.lstrip('@')}/{channel_msg_id}"
        else:
            post_url = f"https://t.me/c/{str(ch).replace('-100', '').lstrip('-')}/{channel_msg_id}"

    sent, failed = 0, 0
    from public_bot.keyboards.inline import manage_registration_kb
    for user in users:
        try:
            kwargs = {}
            if post_url:
                kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
            kwargs["reply_markup"] = manage_registration_kb(show.id)
            await send_with_retry(public_bot.send_message, user.telegram_id, personal_text, **kwargs)
            sent += 1
        except Exception:
            failed += 1

    logger.info("Date-change notifications: sent=%s failed=%s show=%s", sent, failed, show.id)
