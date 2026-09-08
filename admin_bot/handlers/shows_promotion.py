from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()

@router.callback_query(AdminShowActionCb.filter(F.action == "preview"))
async def show_announcement_preview(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from scheduler.jobs import _register_button
    back_kb = InlineKeyboardBuilder()
    back_kb.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())

    preview_text = build_announcement_text(show)
    reg_btn = _register_button(show)
    preview_kb = InlineKeyboardBuilder()
    if reg_btn:
        for row in reg_btn.inline_keyboard:
            for btn in row:
                preview_kb.button(text=btn.text, url=btn.url)
    preview_kb.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    preview_kb.adjust(1)

    if show.poster_file_id:
        await callback.message.answer_photo(
            show.poster_file_id,
            caption=f"👁 <b>Превью анонса:</b>\n\n{preview_text}",
            reply_markup=preview_kb.as_markup(),
        )
    else:
        await callback.message.answer(
            f"👁 <b>Превью анонса:</b>\n\n{preview_text}",
            reply_markup=preview_kb.as_markup(),
        )


def _show_deep_link(show_id: int) -> str:
    return f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show_id}"


def _tracked_show_link(show_id: int, source: str) -> str:
    return f"{_show_deep_link(show_id)}_{source}"


@router.callback_query(AdminShowActionCb.filter(F.action == "link"))
async def send_show_link(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show_id = callback_data.show_id
    if await manageable_show(session, show_id, db_user, is_super_admin) is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    link = _show_deep_link(show_id)
    await callback.message.answer(
        f"🔗 <b>Ссылка на запись:</b>\n\n"
        f"Обычная:\n<code>{link}</code>\n\n"
        f"Instagram:\n<code>{_tracked_show_link(show_id, 'instagram')}</code>\n\n"
        f"Telegram-канал:\n<code>{_tracked_show_link(show_id, 'channel')}</code>\n\n"
        f"Команда:\n<code>{_tracked_show_link(show_id, 'team')}</code>\n\n"
        "Используй отдельные ссылки, чтобы увидеть источники в аналитике.",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "qr"))
async def send_show_qr(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()

    link = _show_deep_link(show_id)
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    date_str = format_local(show.show_date, "%d.%m.%Y")
    caption = (
        f"📱 <b>QR-код для {h(show.title)}</b>\n"
        f"📅 {date_str}\n\n"
        f"Пост в Instagram → человек наводит камеру → "
        f"переходит в бот → видит шоу → записывается."
    )
    await callback.message.answer_photo(
        BufferedInputFile(buf.read(), filename="qr.png"),
        caption=caption,
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "announce"))
async def send_manual_announcement(
    callback: CallbackQuery, callback_data: AdminShowActionCb, bot: Bot, public_bot: Bot,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    if not show.is_active:
        await callback.answer()
        await callback.message.answer("❌ Шоу отменено — анонс нельзя отправить.")
        return
    missing = []
    if not show.poster_text:
        missing.append("📝 текст афиши")
    if not show.poster_file_id:
        missing.append("🖼 изображение")
    if missing:
        await callback.answer(
            f"Нельзя отправить анонс — не заполнено: {', '.join(missing)}.\n"
            "Заполни через ✏️ Редактировать.",
            show_alert=True,
        )
        return

    if not await crud.claim_manual_announcement(session, show_id):
        await callback.answer("Анонс уже был отправлен.", show_alert=True)
        return

    await callback.answer()
    text = build_announcement_text(show)
    try:
        msg_id = await send_to_channel(public_bot, bot, show, text)
        await crud.save_channel_message_id(session, show_id, msg_id)
        await callback.message.answer("✅ Анонс отправлен в канал!")
        refreshed = await crud.get_show(session, show_id)
        if refreshed:
            try:
                await callback.message.edit_reply_markup(reply_markup=show_section_kb(refreshed, "promotion"))
            except Exception:
                pass
        logger.info("manual announcement sent show_id=%s channel_msg_id=%s by admin=%s", show_id, msg_id, callback.from_user.id)
    except Exception as e:
        await crud.release_announcement_claim(session, show_id, "manual")
        logger.exception("Failed to send manual announcement for show_id=%s", show_id)
        await callback.message.answer("❌ Не удалось отправить анонс. Подробности записаны в лог.")


@router.callback_query(AdminShowActionCb.filter(F.action == "remind"))
async def remind_viewers(
    callback: CallbackQuery, callback_data: AdminShowActionCb, public_bot: Bot,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    if not show.is_active:
        await callback.message.answer("❌ Шоу отменено — напоминания нельзя отправить.")
        return
    users = await crud.get_registered_users_for_show(session, show_id)
    channel_msg_id = await crud.get_last_channel_message_id(session, show_id)

    if not users:
        await callback.message.answer("Нет записавшихся зрителей.")
        return

    date_str = format_local(show.show_date)
    location_line = _location_line(show)
    reminder_text = (
        f"🔔 Напоминание!\n\n"
        f"Ты записан(а) на шоу <b>{h(show.title)}</b>\n"
        f"📅 {date_str}\n"
        f"{location_line}"
    )

    post_url = None
    if channel_msg_id:
        ch = settings.ANNOUNCEMENT_CHANNEL_ID
        if ch.startswith("@"):
            post_url = f"https://t.me/{ch.lstrip('@')}/{channel_msg_id}"
        else:
            post_url = f"https://t.me/c/{str(ch).replace('-100', '').lstrip('-')}/{channel_msg_id}"

    sent, failed = 0, 0
    for user in users:
        try:
            kwargs = {}
            if post_url:
                kwargs["link_preview_options"] = LinkPreviewOptions(url=post_url)
            await send_with_retry(public_bot.send_message, user.telegram_id, reminder_text, **kwargs)
            sent += 1
        except Exception:
            failed += 1

    result = f"✅ Напоминание отправлено {sent} зрител{'ю' if sent == 1 else 'ям'}."
    if failed:
        result += f"\n⚠️ Не доставлено: {failed} (бот заблокирован или не начат)."
    await callback.message.answer(result)


@router.callback_query(AdminShowActionCb.filter(F.action == "free_ad"))
async def free_ad(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from scheduler.jobs import build_announcement_text
    from config import settings

    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()

    channels = await crud.get_active_ad_channels(session)
    logger.info("admin %s opened free_ad for show_id=%s channels_count=%s", callback.from_user.id, show_id, len(channels))
    if not channels:
        await callback.message.answer(
            "Нет активных рекламных каналов.\n"
            "Добавь их в Настройки → 📣 Рекламные каналы."
        )
        return

    text = build_announcement_text(show)

    reg_url = f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=show_{show.id}"
    reg_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Записаться на шоу", url=reg_url)
    ]])

    await callback.message.answer(text, reply_markup=reg_kb)

    nav_builder = InlineKeyboardBuilder()
    for ch in channels:
        nav_builder.button(text=f"➡️ {ch.username}", url=ch.url)
    # add a back button to return to the show detail view
    nav_builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    nav_builder.adjust(1)

    await callback.message.answer(
        "⬆️ <b>Перешли сообщение выше</b> в нужный канал:\n"
        "(нажми «Переслать» → выбери канал из списка)",
        reply_markup=nav_builder.as_markup(),
    )
