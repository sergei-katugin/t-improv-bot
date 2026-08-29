from app_logging import get_project_logger

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from admin_bot.callbacks import AdminAdChannelCb
from admin_bot.keyboards.inline import ad_channels_list_kb
from admin_bot.security import deny, is_admin
from admin_bot.telegram_usernames import normalize_telegram_username
from html_utils import h

logger = get_project_logger(__name__)
router = Router()


class AddAdChannelFSM(StatesGroup):
    enter_username = State()


async def _render_channels(target, session: AsyncSession, edit: bool = True):
    channels = await crud.list_ad_channels(session)
    text = (
        "📣 <b>Рекламные каналы</b>\n\n"
        "🟢 — активен (показывается при анонсе)\n"
        "🔴 — отключён\n\n"
        "Нажми на канал, чтобы включить/отключить.\n"
        "🗑 — удалить канал."
    ) if channels else (
        "📣 <b>Рекламные каналы</b>\n\nКаналов пока нет. Добавь первый!"
    )
    kb = ad_channels_list_kb(channels)
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
            return
        except Exception:
            pass
    await target.answer(text, reply_markup=kb)


@router.callback_query(F.data == "admin_adchannels_list")
async def list_ad_channels(callback: CallbackQuery, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    if not is_admin(db_user, is_super_admin):
        await deny(callback)
        return
    await callback.answer()
    await _render_channels(callback.message, session, edit=True)


@router.callback_query(AdminAdChannelCb.filter(F.action == "toggle"))
async def toggle_channel(callback: CallbackQuery, callback_data: AdminAdChannelCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    if not is_admin(db_user, is_super_admin):
        await deny(callback)
        return
    await callback.answer()
    ch = await crud.toggle_ad_channel(session, callback_data.channel_id)
    if ch is None:
        await callback.answer("Канал не найден.", show_alert=True)
        return
    status = "включён 🟢" if ch.is_active else "отключён 🔴"
    await callback.answer(f"{ch.username} {status}", show_alert=True)
    await _render_channels(callback.message, session, edit=True)


@router.callback_query(AdminAdChannelCb.filter(F.action == "delete"))
async def delete_channel(callback: CallbackQuery, callback_data: AdminAdChannelCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    if not is_admin(db_user, is_super_admin):
        await deny(callback)
        return
    await crud.delete_ad_channel(session, callback_data.channel_id)
    logger.info("deleted ad channel id=%s by admin=%s", callback_data.channel_id, callback.from_user.id)
    await callback.answer("Канал удалён.", show_alert=True)
    await _render_channels(callback.message, session, edit=True)


@router.callback_query(F.data == "admin_adchannel_add")
async def add_channel_start(callback: CallbackQuery, state: FSMContext, db_user=None, is_super_admin: bool = False):
    if not is_admin(db_user, is_super_admin):
        await deny(callback)
        return
    await callback.answer()
    await state.set_state(AddAdChannelFSM.enter_username)
    try:
        await callback.message.edit_text(
            "Отправь username канала, например:\n<code>@afishacy</code>"
        )
    except Exception:
        await callback.message.answer(
            "Отправь username канала, например:\n<code>@afishacy</code>"
        )


@router.message(AddAdChannelFSM.enter_username, F.text)
async def add_channel_save(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    if not is_admin(db_user, is_super_admin):
        await state.clear()
        await deny(message)
        return
    raw = message.text.strip()
    username = normalize_telegram_username(raw)
    if not username:
        await message.answer("Неверный формат. Отправь @username канала:")
        return

    await state.clear()
    ch = await crud.add_ad_channel(session, username)
    if ch is None:
        await message.answer(f"Канал <code>{h(username)}</code> уже есть в списке.")
    else:
        await message.answer(f"✅ Добавлен канал {ch.username}")
        logger.info("added ad channel id=%s username=%s by user=%s", ch.id, ch.username, message.from_user.id)
    await _render_channels(message, session, edit=False)
