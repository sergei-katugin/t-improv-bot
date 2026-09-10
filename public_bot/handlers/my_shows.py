from app_logging import get_project_logger
from aiogram import Bot
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import my_shows_kb, shows_list_kb
from public_bot.keyboards.reply import main_menu_kb
from public_bot.callbacks import CancelRegCb
from html_utils import h
from public_bot.handlers.registration import _notify_registration_cancellation, _notify_registration_chat
from time_utils import format_local

router = Router()
logger = get_project_logger(__name__)


@router.message(Command("my_shows"))
@router.message(F.text == "📋 Мои записи")
async def cmd_my_shows(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    await state.clear()
    regs = await crud.get_user_registrations(session, db_user.id)
    all_upcoming = await crud.list_upcoming_shows(session)

    registered_ids = {r.show_id for r in regs}

    if not regs:
        other_shows = all_upcoming
        if other_shows:
            await message.answer(
                "У тебя нет активных записей. Выбери шоу:",
                reply_markup=shows_list_kb(other_shows, set()),
            )
        else:
            await message.answer("У тебя нет активных записей и предстоящих шоу пока нет.")
        return

    await message.answer("📋 <b>Мои записи:</b>", reply_markup=my_shows_kb(regs))

    other_shows = [s for s in all_upcoming if s.id not in registered_ids]
    if other_shows:
        await message.answer(
            "🎭 <b>Другие предстоящие шоу:</b>",
            reply_markup=shows_list_kb(other_shows, set()),
        )


@router.callback_query(CancelRegCb.filter())
async def cancel_registration(callback: CallbackQuery, callback_data: CancelRegCb, db_user: User, session: AsyncSession, admin_bot: Bot):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    reg = await crud.cancel_registration(session, show_id, db_user.id)

    if reg is None:
        await callback.message.answer("Запись не найдена или уже отменена.")
        return

    if show is not None:
        occupied_seats = await crud.count_active_registrations(session, show_id)
        await _notify_registration_cancellation(
            admin_bot,
            show,
            reg.attendee_name,
            reg.guests or 0,
            occupied_seats,
        )
        promoted = await crud.promote_waitlist(session, show_id)
        if promoted:
            promoted_registration, promoted_user = promoted
            try:
                await callback.bot.send_message(
                    promoted_user.telegram_id,
                    f"🎉 Освободилось место! Ты автоматически записан(а) на <b>{h(show.title)}</b>.\n"
                    f"📅 {format_local(show.show_date)}",
                )
            except Exception:
                logger.exception("failed to notify promoted waitlist user show_id=%s user_id=%s", show_id, promoted_user.id)
            promoted_occupied = await crud.count_active_registrations(session, show_id)
            await _notify_registration_chat(
                admin_bot, show, promoted_registration.attendee_name,
                promoted_registration.guests or 0, "waitlist", promoted_occupied,
                promoted_user,
            )

    show_title = show.title if show else "шоу"

    regs = await crud.get_user_registrations(session, db_user.id)
    all_upcoming = await crud.list_upcoming_shows(session)

    from public_bot.keyboards.reply import main_menu_kb as _menu_kb
    updated_menu = _menu_kb(has_shows=bool(all_upcoming), has_regs=bool(regs))

    registered_ids = {r.show_id for r in regs}
    other_shows = [s for s in all_upcoming if s.id not in registered_ids]

    is_photo = bool(callback.message.photo)
    if is_photo:
        try:
            await callback.message.delete()
        except Exception:
            pass

    if regs:
        if is_photo:
            await callback.message.answer(
                f"✅ Запись на <b>{h(show_title)}</b> отменена.\n\n📋 <b>Оставшиеся записи:</b>",
                reply_markup=my_shows_kb(regs),
            )
        else:
            await callback.message.edit_text(
                f"✅ Запись на <b>{h(show_title)}</b> отменена.\n\n📋 <b>Оставшиеся записи:</b>",
                reply_markup=my_shows_kb(regs),
            )
    else:
        if is_photo:
            await callback.message.answer(
                f"✅ Запись на <b>{h(show_title)}</b> отменена.",
                reply_markup=updated_menu,
            )
        else:
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass
            await callback.message.answer(
                f"✅ Запись на <b>{h(show_title)}</b> отменена.",
                reply_markup=updated_menu,
            )

    if other_shows:
        await callback.message.answer(
            "🎭 <b>Предстоящие шоу:</b>",
            reply_markup=shows_list_kb(other_shows, registered_ids),
        )
    logger.info("user %s cancelled registration for show_id=%s", db_user.id, show_id)
