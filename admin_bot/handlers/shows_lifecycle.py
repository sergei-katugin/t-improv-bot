from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()

@router.callback_query(AdminShowActionCb.filter(F.action == "cancel"))
async def cancel_show_confirm(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()

    await callback.message.edit_text(
        f"🚫 <b>Отменить шоу?</b>\n\n"
        f"🎭 {h(show.title)}\n"
        f"📅 {format_local(show.show_date)}\n\n"
        f"Все записанные зрители получат уведомление об отмене.\n"
        f"В канал будет отправлено сообщение с перечёркнутым анонсом.\n\n"
        f"<b>Это действие нельзя отменить.</b>",
        reply_markup=confirm_kb(AdminShowActionCb(action="confirm_cancel", show_id=show_id).pack(), AdminShowActionCb(action="open", show_id=show_id).pack()),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "delete"))
async def delete_show_confirm(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    if not is_admin(db_user, is_super_admin):
        await deny(callback, "Удалять шоу могут только администраторы.")
        return
    await callback.answer()

    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.answer("Шоу не найдено.")
        return

    await callback.message.edit_text(
        f"🗑 <b>Удалить шоу навсегда?</b>\n\n"
        f"🎭 {h(show.title)}\n"
        f"📅 {format_local(show.show_date)}\n\n"
        f"Это удалит все записи, лог анонсов и связанные данные.\n"
        f"<b>Действие необратимо.</b>",
        reply_markup=confirm_kb(AdminShowActionCb(action="confirm_delete", show_id=show_id).pack(), AdminShowActionCb(action="open", show_id=show_id).pack()),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "confirm_delete"))
async def delete_show_execute(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    if not is_admin(db_user, is_super_admin):
        await deny(callback, "Удалять шоу могут только администраторы.")
        return
    await callback.answer()

    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.edit_text("Шоу не найдено.")
        return

    deleted = await crud.delete_show(session, show_id)
    if not deleted:
        await callback.message.edit_text("Не удалось удалить шоу — возможно, есть связанные записи. Попробуйте позже.")
        return

    await callback.message.edit_text(f"🗑 Шоу <b>{h(show.title)}</b> удалено навсегда.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "confirm_cancel"))
async def cancel_show_execute(
    callback: CallbackQuery, callback_data: AdminShowActionCb, bot: Bot, public_bot: Bot,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    if not show.is_active:
        await callback.message.edit_text("Шоу не найдено или уже отменено.")
        return
    was_announced = await crud.has_any_announcement_been_sent(session, show_id)
    reply_to = await crud.get_last_channel_message_id(session, show_id)
    users = await crud.get_registered_users_for_show(session, show_id)
    await crud.update_show(session, show_id, is_active=False)
    logger.info("show cancelled id=%s by admin=%s", show_id, callback.from_user.id)

    await callback.message.edit_text(f"🚫 Шоу <b>{h(show.title)}</b> отменено.")

    if was_announced:
        channel_text = (
            f"🚫 <b>Шоу отменено</b>\n\n"
            f"🎭 <s>{h(show.title)}</s>\n"
            f"📅 <s>{format_local(show.show_date)}</s>\n"
            f"📍 <s>{h(show.location)}, {h(show.city)}</s>\n\n"
            f"Приносим извинения за неудобства. Следите за новыми анонсами!"
        )
        try:
            await send_to_channel(
                public_bot, bot, show, channel_text,
                with_button=False, reply_to_message_id=reply_to,
            )
            logger.info("posted cancellation to channel for show %s reply_to=%s", show_id, reply_to)
        except Exception:
            logger.exception("Failed to post cancellation to channel for show %s", show_id)

    # Personal DMs
    personal_text = (
        f"❌ <b>Шоу отменено</b>\n\n"
        f"К сожалению, мероприятие, на которое ты записан(а), отменено:\n\n"
        f"🎭 <b>{h(show.title)}</b>\n"
        f"📅 {format_local(show.show_date)}\n"
        f"{_location_line(show)}\n\n"
        f"Приносим извинения! Следи за новыми анонсами 🎭"
    )
    ch = settings.ANNOUNCEMENT_CHANNEL_ID
    channel_url = f"https://t.me/{ch.lstrip('@')}" if ch.startswith("@") else None
    cancel_kb = None
    if channel_url:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)
        ]])
    sent, failed = 0, 0
    for user in users:
        try:
            await send_with_retry(public_bot.send_message, user.telegram_id, personal_text, reply_markup=cancel_kb)
            sent += 1
        except Exception:
            failed += 1

    logger.info("cancellation notifications for show %s sent=%s failed=%s", show_id, sent, failed)

    result = f"✅ Уведомление об отмене отправлено {sent} зрител{'ю' if sent == 1 else 'ям'}."
    if failed:
        result += f"\n⚠️ Не доставлено: {failed}."
    await callback.message.answer(result)


@router.callback_query(AdminShowActionCb.filter(F.action == "restore"))
async def restore_show(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    if show.is_active:
        await callback.message.answer("Шоу не найдено или уже активно.")
        return
    await crud.update_show(session, show_id, is_active=True)
    logger.info("restored show id=%s by admin=%s", show_id, callback.from_user.id)

    show = await crud.get_show(session, show_id)

    tg_id = callback.from_user.id
    is_creator = (show.creator and show.creator.telegram_id == tg_id) or tg_id in ADMIN_ID_LIST
    kb = show_detail_kb(show, is_creator, can_delete=(callback.from_user.id in ADMIN_ID_LIST))

    await callback.message.edit_text(
        f"✅ Шоу <b>{h(show.title)}</b> восстановлено и снова активно.",
        reply_markup=kb,
    )
