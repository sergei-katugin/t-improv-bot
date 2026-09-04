from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User
from db import crud
from public_bot.callbacks import RegisterCb, CancelRegCb
from public_bot.show_utils import NO_LINK_PREVIEW, show_text, render_show_detail

router = Router()


PRIVACY_TEXT = (
    "🔐 <b>Политика конфиденциальности</b>\n\n"
    "Бот сохраняет Telegram ID, имя и username, чтобы показывать твои записи. "
    "Для работы регистрации также хранятся имя зрителя, количество гостей, настройки напоминаний, "
    "подтверждение участия, отметка о посещении и добровольный отзыв.\n\n"
    "Данные используются только для организации шоу, уведомлений, управления вместимостью и статистики. "
    "Они не продаются и не используются для сторонней рекламы. Доступ к спискам имеют только организаторы соответствующего шоу и администраторы.\n\n"
    "Данные хранятся, пока нужны для работы сервиса. Удалить свои персональные данные можно командой /delete_me. "
    "Если пользователь создавал шоу или команды, их история сохранится с обезличенным создателем."
)


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "ℹ️ <b>Помощь</b>\n\n"
        "/start — открыть ближайшее шоу\n"
        "/shows — все предстоящие шоу\n"
        "/my_shows — мои записи\n"
        "/settings — настройки и данные\n"
        "/privacy — политика конфиденциальности"
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message):
    await message.answer(
        "⚙️ <b>Настройки</b>\n\n"
        "Напоминания настраиваются отдельно в каждой активной записи через /my_shows.\n\n"
        "Данные: /privacy\nУдалить мои данные: /delete_me"
    )


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(PRIVACY_TEXT)


@router.message(Command("delete_me"))
async def cmd_delete_me(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Да, удалить мои данные", callback_data="privacy_delete_confirm"),
    ], [
        InlineKeyboardButton(text="Отмена", callback_data="privacy_delete_cancel"),
    ]])
    await message.answer(
        "🗑 <b>Удалить персональные данные?</b>\n\n"
        "Будут удалены профиль, записи и отзывы. Это действие нельзя отменить.",
        reply_markup=kb,
    )


@router.callback_query(F.data == "privacy_delete_cancel")
async def cancel_delete_me(callback: CallbackQuery):
    await callback.answer("Отменено")
    await callback.message.edit_text("Удаление данных отменено.")


@router.callback_query(F.data == "privacy_delete_confirm")
async def confirm_delete_me(callback: CallbackQuery, db_user: User, session: AsyncSession):
    await callback.answer()
    await crud.delete_or_anonymize_user_data(session, db_user)
    await callback.message.edit_text(
        "✅ Твои персональные данные удалены. При следующем обращении бот создаст новый пустой профиль."
    )


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

    if payload.startswith("door_"):
        show_id = await crud.consume_checkin_invite(session, payload[5:], db_user.id)
        if show_id is None:
            await message.answer("❌ Ссылка недействительна, уже использована или устарела.", reply_markup=menu_kb)
        else:
            from config import settings
            admin_username = settings.ADMIN_BOT_USERNAME.lstrip("@")
            await message.answer(
                "✅ Доступ сотрудника входа выдан только к этому шоу.\n\n"
                "Открой служебного бота и запусти режим входа:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="🚪 Открыть режим входа",
                        url=f"https://t.me/{admin_username}?start=door_{show_id}",
                    )
                ]]),
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
