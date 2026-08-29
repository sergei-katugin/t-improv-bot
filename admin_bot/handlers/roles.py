from app_logging import get_project_logger

from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import crud
from db.models import UserRole
from admin_bot.keyboards.inline import organizers_list_kb, roles_menu_kb
from admin_bot.callbacks import AdminRevokeCb

logger = get_project_logger(__name__)
router = Router()


@router.message(Command("roles"))
@router.message(F.text == "👥 Управление доступом")
@router.callback_query(F.data == "admin_roles_menu")
async def cmd_roles(event, state: FSMContext, is_super_admin: bool = False):
    if not is_super_admin:
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Только для администраторов.", show_alert=True)
        else:
            await event.answer("⛔ Только администраторы могут управлять доступом.")
        return
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    text = "👥 <b>Управление доступом</b>\n\nВыдай доступ на просмотр записей другим пользователям:"
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=roles_menu_kb())
    else:
        await msg.edit_text(text, reply_markup=roles_menu_kb())


@router.callback_query(F.data == "admin_grant_organizer")
async def grant_viewer_link(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    invite = await crud.create_invite_token(session, UserRole.organizer)
    logger.info("created invite id=%s role=%s by admin=%s", invite.id, invite.role, callback.from_user.id)

    link = f"https://t.me/{settings.PUBLIC_BOT_USERNAME}?start=inv_{invite.token}"
    await callback.message.edit_text(
        "🔗 <b>Одноразовая ссылка для доступа:</b>\n\n"
        f"<code>{link}</code>\n\n"
        "Отправь её нужному человеку. Когда они перейдут по ссылке — "
        "автоматически получат доступ на просмотр записей. Ссылка сгорает после первого использования.",
        reply_markup=roles_menu_kb(),
    )


@router.callback_query(F.data == "admin_noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "admin_list_organizers")
async def list_viewers(callback: CallbackQuery, session: AsyncSession):
    await callback.answer()
    viewers = await crud.get_all_organizers(session)

    if not viewers:
        try:
            await callback.message.edit_text(
                "Нет пользователей с доступом.",
                reply_markup=roles_menu_kb(),
            )
        except TelegramBadRequest:
            pass
        return

    try:
        await callback.message.edit_text(
            "👥 <b>Пользователи с доступом</b>\n👑 — администратор, ❌ — отозвать доступ:",
            reply_markup=organizers_list_kb(viewers),
        )
    except TelegramBadRequest:
        pass


@router.callback_query(AdminRevokeCb.filter())
async def revoke_viewer(callback: CallbackQuery, callback_data: AdminRevokeCb, session: AsyncSession):
    target_id = callback_data.telegram_id
    await callback.answer()

    user = await crud.set_user_role(session, target_id, UserRole.user)
    logger.info("revoked organizer role for telegram_id=%s by admin=%s", target_id, callback.from_user.id)

    name = (user.first_name or user.username or str(target_id)) if user else str(target_id)
    await callback.message.edit_text(f"✅ Доступ пользователя <b>{name}</b> отозван.")
