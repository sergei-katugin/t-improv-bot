from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db import crud
from public_bot.callbacks import RegisterCb, CancelRegCb
from public_bot.show_utils import NO_LINK_PREVIEW, show_text, render_show_detail

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, db_user: User, session: AsyncSession, menu_kb):
    await state.clear()
    args = message.text.split(maxsplit=1)
    payload = args[1] if len(args) > 1 else ""

    if payload.startswith("inv_"):
        token = payload[4:]
        invite = await crud.consume_invite_token(session, token, db_user.id)
        if invite:
            await message.answer(
                "✅ Тебе выдан доступ на просмотр записей шоу!\n\n"
                "Используй бот @ImprovCypBot чтобы посмотреть список участников.",
                reply_markup=menu_kb,
            )
        else:
            await message.answer(
                "❌ Ссылка недействительна или уже была использована.",
                reply_markup=menu_kb,
            )
        return

    if payload.startswith("show_"):
        show_payload = payload[5:]
        show_id_raw, _, source = show_payload.partition("_")
        try:
            show_id = int(show_id_raw)
        except ValueError:
            show_id = None
        if show_id:
            if source:
                await state.update_data(registration_source=source[:64], registration_source_show_id=show_id)
            await render_show_detail(message, show_id, db_user, session)
            return

    # No payload — show nearest upcoming show directly
    shows = await crud.list_upcoming_shows(session)

    if not shows:
        await message.answer(
            "👋 Привет! Сейчас нет предстоящих шоу. Загляни позже! 🎭",
            reply_markup=menu_kb,
        )
        return

    show = shows[0]
    active_count = await crud.count_active_registrations(session, show.id)
    reg = await crud.get_registration(session, show.id, db_user.id)

    seats_left = max(0, show.max_seats - active_count)
    is_registered = reg is not None and not reg.is_cancelled

    text = show_text(show, seats_left, reg=reg)

    builder = InlineKeyboardBuilder()
    if seats_left > 0 and not is_registered:
        builder.button(text="📝 Записаться", callback_data=RegisterCb(show_id=show.id).pack())
    elif is_registered:
        builder.button(text="❌ Отменить запись", callback_data=CancelRegCb(show_id=show.id).pack())
    else:
        builder.button(text="😔 Мест нет", callback_data="pub_no_seats")
    if len(shows) > 1:
        builder.button(text="🎭 Другое шоу", callback_data="pub_shows_list")
    builder.adjust(1)

    await message.answer(
        text,
        reply_markup=builder.as_markup(),
        link_preview_options=NO_LINK_PREVIEW,
    )
