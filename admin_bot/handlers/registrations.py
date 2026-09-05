from __future__ import annotations

import csv
import io

from app_logging import get_project_logger

from aiogram import Router, F
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.base import AsyncSessionLocal
from db.models import UserRole
from config import settings
from admin_bot.keyboards.inline import (
    checkin_counter_kb, checkin_kb, checkin_mode_kb, party_count_kb,
    registration_chat_kb, registrations_kb,
)
from admin_bot.keyboards.reply import flow_context_kb, registration_channel_picker_kb, registrations_context_kb, show_context_kb
from admin_bot.callbacks import AdminCheckinCb, AdminManualCheckinCb, AdminPartyCountCb, AdminShowActionCb
from admin_bot.security import checkin_accessible_show, deny, manageable_show
from html_utils import h


def _can_manage(is_super_admin: bool, db_user, show_creator_id: int | None = None) -> bool:
    if is_super_admin or (db_user is not None and db_user.role == UserRole.admin):
        return True
    if show_creator_id is not None and db_user is not None:
        return db_user.id == show_creator_id
    return False

logger = get_project_logger(__name__)
router = Router()


@router.my_chat_member()
async def registration_chat_membership_updated(event: ChatMemberUpdated, bot) -> None:
    """Remember a chat when an organizer adds the admin bot and explain the next step."""
    active_statuses = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR}
    if event.new_chat_member.status not in active_statuses or event.old_chat_member.status in active_statuses:
        return
    if event.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        return
    try:
        actor_member = await bot.get_chat_member(event.chat.id, event.from_user.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        return
    if actor_member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        return
    async with AsyncSessionLocal() as session:
        owner = await crud.get_user_by_telegram_id(session, event.from_user.id)
        if owner is None or owner.role not in {UserRole.organizer, UserRole.admin}:
            logger.info("registration chat not remembered: inviter has no organizer access telegram_id=%s chat_id=%s", event.from_user.id, event.chat.id)
            return
        await crud.remember_registration_chat(session, owner.id, event.chat)
    bot_url = f"https://t.me/{settings.ADMIN_BOT_USERNAME.lstrip('@')}?start=connected_chat"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть управление афишами", url=bot_url),
    ]])
    try:
        await bot.send_message(
            event.chat.id,
            "✅ <b>Чат подключён</b>\n\nТеперь его можно выбрать в поле «Чат записей» при создании или редактировании афиши.",
            reply_markup=keyboard,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.warning("connected registration chat saved but welcome could not be sent chat_id=%s", event.chat.id)


@router.message(Command("connect_chat"))
async def remember_current_registration_chat(message: Message, session: AsyncSession, bot, db_user=None):
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Добавь меня в нужную группу и вызови там /connect_chat.")
        return
    try:
        member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Не удалось проверить твои права в этом чате.")
        return
    if member.status not in {ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
        await message.answer("Подключить чат может только его администратор.")
        return
    try:
        test = await bot.send_message(message.chat.id, "✅ Чат сохранён. Теперь его можно выбрать в Mini App в разделе «Чат записей».")
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Я не могу отправлять сообщения в этот чат. Проверь мои права.")
        return
    await crud.remember_registration_chat(session, db_user.id, message.chat)
    logger.info("registration chat remembered owner_user_id=%s chat_id=%s test_message_id=%s", db_user.id, message.chat.id, test.message_id)


def _csv_cell(value) -> str:
    """Prevent spreadsheet programs from evaluating exported user text as formulas."""
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text


class AddManualFSM(StatesGroup):
    names = State()


class DeleteManualFSM(StatesGroup):
    select = State()


class RegistrationChatFSM(StatesGroup):
    chat = State()


class CheckinSearchFSM(StatesGroup):
    query = State()


async def _current_show_from_state(state: FSMContext, session: AsyncSession, db_user, is_super_admin: bool):
    show_id = (await state.get_data()).get("current_show_id")
    return await manageable_show(session, show_id, db_user, is_super_admin) if show_id else None


@router.message(F.text == "➕ Добавить зрителя")
async def quick_add_attendee(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _current_show_from_state(state, session, db_user, is_super_admin)
    if show is None:
        await message.answer("Сначала открой шоу из афиши.", reply_markup=show_context_kb())
        return
    await state.set_state(AddManualFSM.names)
    await state.update_data(show_id=show.id, manual_source="manual", current_show_id=show.id)
    await message.answer(
        "Отправь зрителей по одному на строку. Контакт можно указать после <code>|</code>, "
        "например: <code>Анна | @anna</code>.", reply_markup=flow_context_kb(),
    )


@router.message(F.text == "🔔 Чат записей")
async def quick_registration_chat(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _current_show_from_state(state, session, db_user, is_super_admin)
    if show is None:
        await message.answer("Сначала открой шоу из афиши.", reply_markup=show_context_kb())
        return
    await state.set_state(RegistrationChatFSM.chat)
    await state.update_data(show_id=show.id, current_show_id=show.id)
    await message.answer(
        "🔔 <b>Чат записей</b>\n\nНажми «Выбрать канал». Telegram покажет каналы, "
        "которыми ты управляешь, добавит этого бота и запросит только право публикации. "
        "Искать @username или ID не нужно.",
        reply_markup=registration_channel_picker_kb(),
    )


@router.message(RegistrationChatFSM.chat, F.text == "⏭ Пропустить")
async def skip_registration_chat(message: Message, state: FSMContext):
    data = await state.get_data()
    show_id = data.get("show_id") or data.get("current_show_id")
    await state.clear()
    await state.update_data(current_show_id=show_id, reply_context="show")
    await message.answer("Чат записей пока не подключён. Это можно сделать позже в разделе «Записи».", reply_markup=show_context_kb())


@router.message(F.text == "🎟 Режим входа")
async def quick_checkin_mode(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _current_show_from_state(state, session, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await message.answer("Режим входа для этого шоу выключен.", reply_markup=registrations_context_kb())
        return
    await message.answer(
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n\nВыбери способ учёта:",
        reply_markup=checkin_mode_kb(show.id),
    )


async def _render_registrations(target, show_id: int, session: AsyncSession, edit: bool = True, is_super_admin: bool = False, db_user=None):
    show = await crud.get_show(session, show_id)
    regs = await crud.get_show_registrations(session, show_id)
    manual = await crud.get_manual_attendees(session, show_id)

    if show is None:
        return

    active = [r for r in regs if not r.is_cancelled]
    cancelled = [r for r in regs if r.is_cancelled]
    total = sum(1 + (r.guests or 0) for r in active) + len(manual)
    confirmed_count = sum(1 + (r.guests or 0) for r in active if r.confirmed is True)
    declined_count = sum(1 for r in active if r.confirmed is False)

    lines = [f"👥 <b>Записи на «{h(show.title)}»</b>", f"Всего: {total} / {show.max_seats}"]
    if confirmed_count or declined_count:
        lines.append(f"✅ Подтвердили: {confirmed_count}  ❌ Не придут: {declined_count}")
    lines.append("")

    n = 1
    for r in active:
        uname = f" (@{h(r.user.username)})" if r.user.username else ""
        guests = r.guests or 0
        guest_str = f" +{guests}" if guests > 0 else ""
        lines.append(f"{n}. {h(r.attendee_name)}{guest_str}{uname}")
        n += 1
    for att in manual:
        notify_status = "уведомлён(а)" if att.notification_confirmed_at else "уведомить вручную"
        lines.append(f"{n}. {h(att.name)} <i>[{notify_status}]</i>")
        n += 1
    if cancelled:
        lines.append(f"\n❌ Отменённых: {len(cancelled)}")

    text = "\n".join(lines)
    if len(text) > 4000:
        cut = text.rfind("\n", 0, 3990)
        text = text[:cut] + "\n..."

    kb = registrations_kb(show_id, manual, can_manage=_can_manage(is_super_admin, db_user, show.creator_id if show else None))
    if edit:
        try:
            await target.edit_text(text, reply_markup=kb)
        except Exception:
            await target.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


@router.callback_query(AdminShowActionCb.filter(F.action == "regs"))
async def show_registrations(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    if await manageable_show(session, show_id, db_user, is_super_admin) is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await _render_registrations(callback.message, show_id, session, edit=True, is_super_admin=is_super_admin, db_user=db_user)
    await state.update_data(current_show_id=show_id, reply_context="registrations")
    await callback.message.answer("Действия с записями:", reply_markup=registrations_context_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "reg_chat"))
async def configure_registration_chat(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await state.set_state(RegistrationChatFSM.chat)
    await state.update_data(show_id=show.id)
    current = f"\n\nСейчас подключён: <b>{h(show.registration_chat_title or show.registration_chat_id)}</b>" if show.registration_chat_id else ""
    await callback.message.edit_text(
        "🔔 <b>Чат записей</b>\n\n"
        "Нажми <b>«Выбрать канал»</b> ниже. Telegram покажет каналы, которыми ты управляешь, "
        "сам добавит этого бота и запросит только право публикации сообщений.\n\n"
        "Никакой @username или числовой ID искать не нужно. После подключения бот отправит тестовое сообщение."
        f"{current}",
        reply_markup=registration_chat_kb(
            show.id, bool(show.registration_chat_id), show.registration_chat_name_mode,
        ),
    )
    await callback.message.answer(
        "Выбери канал системной кнопкой Telegram. Если канал не появляется, у тебя нет прав администратора в нём.",
        reply_markup=registration_channel_picker_kb(),
    )


async def _save_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, show, target, display_name: str) -> None:
    try:
        chat = await bot.get_chat(target)
        test = await bot.send_message(
            chat.id,
            f"✅ Чат подключён к шоу «{h(show.title)}». Здесь будут появляться новые записи.",
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer(
            "Не получилось написать в этот канал. Проверь, что бот добавлен с правом публикации."
        )
        return
    title = getattr(chat, "title", None) or getattr(chat, "username", None) or display_name
    await crud.update_show(
        session, show.id, registration_chat_id=chat.id, registration_chat_title=title,
    )
    await state.clear()
    await state.update_data(current_show_id=show.id, reply_context="registrations")
    await message.answer(f"✅ Чат записей подключён: <b>{h(title)}</b>.", reply_markup=registrations_context_kb())
    logger.info("registration chat configured show_id=%s chat_id=%s test_message_id=%s", show.id, chat.id, test.message_id)


@router.message(RegistrationChatFSM.chat, F.chat_shared)
async def save_shared_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, is_super_admin: bool = False, db_user=None):
    shared = message.chat_shared
    if shared.request_id != 7101:
        return
    show_id = (await state.get_data()).get("show_id")
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await state.clear()
        await message.answer("⛔ Нет доступа к этому шоу.")
        return
    try:
        shared_chat = await bot.get_chat(shared.chat_id)
        await crud.remember_registration_chat(session, db_user.id, shared_chat)
    except (TelegramBadRequest, TelegramForbiddenError):
        await message.answer("Не удалось получить выбранный канал. Попробуй выбрать его ещё раз.")
        return
    await _save_registration_chat(
        message, state, session, bot, show, shared.chat_id,
        shared.title or (f"@{shared.username}" if shared.username else str(shared.chat_id)),
    )


@router.message(RegistrationChatFSM.chat, F.text)
async def save_registration_chat(message: Message, state: FSMContext, session: AsyncSession, bot, is_super_admin: bool = False, db_user=None):
    await message.answer("Выбери канал системной кнопкой Telegram — искать username или ID не нужно.", reply_markup=registration_channel_picker_kb())


@router.callback_query(AdminShowActionCb.filter(F.action == "reg_chat_clear"))
async def clear_registration_chat(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await crud.update_show(session, show.id, registration_chat_id=None, registration_chat_title=None)
    await state.clear()
    await callback.answer("Чат отключён")
    await callback.message.edit_text("🔕 Уведомления о новых записях для этого шоу отключены.")


@router.callback_query(AdminShowActionCb.filter(F.action.in_({"reg_name_short", "reg_name_full"})))
async def change_registration_chat_name_mode(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    mode = "full" if callback_data.action == "reg_name_full" else "short"
    show = await crud.update_show(session, show.id, registration_chat_name_mode=mode)
    await callback.answer("Формат имён обновлён")
    await callback.message.edit_reply_markup(
        reply_markup=registration_chat_kb(show.id, bool(show.registration_chat_id), mode)
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "manual_notified"))
async def confirm_manual_notifications(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    count = await crud.confirm_manual_attendees_notified(session, show.id)
    await callback.answer(f"Отмечено: {count}")
    await callback.message.edit_text(
        f"✅ <b>Зрители уведомлены вручную</b>\n\nШоу: «{h(show.title)}»\nОтмечено записей: {count}"
    )


async def _render_checkin(target, show_id: int, session: AsyncSession) -> None:
    show = await crud.get_show(session, show_id)
    if show is None or not show.checkin_enabled:
        await target.answer("Режим входа для этого шоу выключен.")
        return
    regs = await crud.get_show_registrations(session, show_id)
    manual = await crud.get_manual_attendees(session, show_id)
    active = [reg for reg in regs if not reg.is_cancelled]
    arrived = sum(reg.checked_in_count or 0 for reg in active) + sum(item.checked_in_count or 0 for item in manual)
    total = sum(1 + (reg.guests or 0) for reg in active) + len(manual)
    visible_regs = active[:50]
    visible_manual = manual[:max(0, 50 - len(visible_regs))]
    text = (
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n"
        f"Пришли: {arrived} / {total}\n\n"
        "Нажми на участника, чтобы изменить отметку."
    )
    if len(active) + len(manual) > 50:
        text += "\n\nПоказаны первые 50 записей. Для остальных используй поиск по имени."
    try:
        await target.edit_text(text, reply_markup=checkin_kb(show_id, visible_regs, visible_manual))
    except Exception:
        await target.answer(text, reply_markup=checkin_kb(show_id, visible_regs, visible_manual))


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_invite"))
async def create_checkin_staff_invite(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    session: AsyncSession,
    db_user=None,
    is_super_admin: bool = False,
):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    from config import settings
    invite = await crud.create_checkin_invite(session, show.id, settings.INVITE_TTL_HOURS)
    link = f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=door_{invite.token}"
    await callback.answer()
    await callback.message.answer(
        f"🚪 <b>Доступ сотруднику входа</b>\n\n"
        f"Отправь сотруднику одноразовую ссылку:\n<code>{link}</code>\n\n"
        f"Она действует {settings.INVITE_TTL_HOURS} ч. и выдаёт доступ только к отметке посетителей этого шоу. "
        "Редактирование шоу, списки и аналитика останутся закрыты.",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin"))
async def show_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await callback.message.edit_text(
        f"🎟 <b>Режим входа: {h(show.title)}</b>\n\nВыбери способ учёта посетителей:",
        reply_markup=checkin_mode_kb(show.id),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_named"))
async def show_named_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    if show.checkin_mode == "counter" and (show.checkin_counter or 0) > 0:
        await callback.answer("Счётчик уже используется. Режим нельзя сменить во время входа.", show_alert=True)
        return
    await crud.update_show(session, show.id, checkin_mode="named")
    await callback.answer()
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminShowActionCb.filter(F.action == "checkin_search"))
async def start_checkin_search(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    await callback.answer()
    await state.set_state(CheckinSearchFSM.query)
    await state.update_data(checkin_show_id=show.id)
    await callback.message.edit_text(
        "🔍 Введи имя, фамилию или Telegram username зрителя:",
    )


@router.message(CheckinSearchFSM.query, F.text)
async def find_checkin_attendee(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show_id = (await state.get_data()).get("checkin_show_id")
    show = await checkin_accessible_show(session, show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await state.clear()
        await message.answer("⛔ Режим входа недоступен.")
        return
    query = message.text.strip().lstrip("@").casefold()
    regs = [item for item in await crud.get_show_registrations(session, show.id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show.id)
    matches = []
    for item in regs:
        username = (item.user.username or "").casefold()
        if query in item.attendee_name.casefold() or query in username:
            matches.append(("r", item.id, item.attendee_name, item.checked_in_count or 0, 1 + (item.guests or 0)))
    for item in manual:
        if query in item.name.casefold():
            matches.append(("m", item.id, item.name, item.checked_in_count or 0, 1))
    builder = InlineKeyboardBuilder()
    for kind, item_id, name, actual, booked in matches[:20]:
        callback_data = (
            AdminCheckinCb(show_id=show.id, registration_id=item_id).pack()
            if kind == "r" else AdminManualCheckinCb(show_id=show.id, attendee_id=item_id).pack()
        )
        builder.button(text=f"{'✅' if actual else '⬜️'} {name} — {actual}/{booked}", callback_data=callback_data)
    builder.button(text="🔍 Искать снова", callback_data=AdminShowActionCb(action="checkin_search", show_id=show.id).pack())
    builder.button(text="📋 Весь список", callback_data=AdminShowActionCb(action="checkin_named", show_id=show.id).pack())
    builder.adjust(1)
    await state.clear()
    await message.answer(
        f"Найдено: {len(matches)}" if matches else "Никого не найдено.",
        reply_markup=builder.as_markup(),
    )


async def _notify_checkin_milestones(bot, session: AsyncSession, show, arrived: int) -> None:
    claim = await crud.claim_checkin_milestones(session, show.id, arrived)
    if claim is None:
        return
    previous, highest, chat_id, title = claim
    try:
        for milestone in range(previous + 10, highest + 1, 10):
            await bot.send_message(
                chat_id,
                f"🎟 На шоу «{h(title)}» пришли уже <b>{milestone}</b> человек.",
            )
    except Exception:
        await crud.release_checkin_milestones(session, show.id, highest, previous)
        logger.exception("failed to send check-in milestone show_id=%s", show.id)


async def _named_arrived_total(session: AsyncSession, show_id: int) -> int:
    regs = [item for item in await crud.get_show_registrations(session, show_id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show_id)
    return sum(item.checked_in_count or 0 for item in regs) + sum(item.checked_in_count or 0 for item in manual)


@router.callback_query(AdminCheckinCb.filter())
async def toggle_checkin(callback: CallbackQuery, callback_data: AdminCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    regs = await crud.get_show_registrations(session, show.id)
    reg = next((item for item in regs if item.id == callback_data.registration_id and not item.is_cancelled), None)
    if reg is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    booked = 1 + (reg.guests or 0)
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{h(reg.attendee_name)}</b>\nЗаписано: {booked}\nПришло: {reg.checked_in_count or 0}\n\nСколько человек пришло фактически?",
        reply_markup=party_count_kb(show.id, "r", reg.id, booked, reg.checked_in_count or 0),
    )


@router.callback_query(AdminManualCheckinCb.filter())
async def toggle_manual_checkin(callback: CallbackQuery, callback_data: AdminManualCheckinCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    manual = await crud.get_manual_attendees(session, show.id)
    attendee = next((item for item in manual if item.id == callback_data.attendee_id), None)
    if attendee is None:
        await callback.answer("Участник не найден", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"👤 <b>{h(attendee.name)}</b>\nЗаписано: 1\nПришло: {attendee.checked_in_count or 0}\n\nСколько человек пришло фактически?",
        reply_markup=party_count_kb(show.id, "m", attendee.id, 1, attendee.checked_in_count or 0),
    )


@router.callback_query(AdminPartyCountCb.filter())
async def set_party_checkin(callback: CallbackQuery, callback_data: AdminPartyCountCb, session: AsyncSession, bot, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    if callback_data.kind == "r":
        item = await crud.set_registration_checkin_count(session, show.id, callback_data.item_id, callback_data.count)
    elif callback_data.kind == "m":
        item = await crud.set_manual_checkin_count(session, show.id, callback_data.item_id, callback_data.count)
    else:
        item = None
    if item is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    arrived = await _named_arrived_total(session, show.id)
    await _notify_checkin_milestones(bot, session, show, arrived)
    await callback.answer(f"Пришло: {callback_data.count}")
    await _render_checkin(callback.message, show.id, session)


@router.callback_query(AdminShowActionCb.filter(F.action.in_({"checkin_counter", "count_add1", "count_add5", "count_sub1"})))
async def counter_checkin(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, bot, db_user=None, is_super_admin: bool = False):
    show = await checkin_accessible_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None or not show.checkin_enabled:
        await deny(callback, "⛔ Режим входа недоступен.")
        return
    delta = {"checkin_counter": 0, "count_add1": 1, "count_add5": 5, "count_sub1": -1}[callback_data.action]
    if show.checkin_mode != "counter":
        if await _named_arrived_total(session, show.id) > 0:
            await callback.answer("Учёт по именам уже начат. Режим нельзя сменить во время входа.", show_alert=True)
            return
        show = await crud.update_show(session, show.id, checkin_mode="counter")
    if delta:
        show = await crud.change_checkin_counter(session, show.id, delta)
    await _notify_checkin_milestones(bot, session, show, show.checkin_counter or 0)
    await callback.answer()
    await callback.message.edit_text(
        f"🔢 <b>Простой счётчик</b>\n\nФактически вошли: <b>{show.checkin_counter or 0}</b>",
        reply_markup=checkin_counter_kb(show.id),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "analytics"))
async def show_analytics(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = await crud.get_show_registrations(session, show.id)
    manual = await crud.get_manual_attendees(session, show.id)
    feedback = await crud.get_show_feedback(session, show.id)
    active = [reg for reg in regs if not reg.is_cancelled]
    people = sum(1 + (reg.guests or 0) for reg in active) + len(manual)
    cancelled = len([reg for reg in regs if reg.is_cancelled])
    confirmed = sum(1 + (reg.guests or 0) for reg in active if reg.confirmed is True)
    arrived = (
        show.checkin_counter or 0
        if show.checkin_mode == "counter"
        else sum(reg.checked_in_count or 0 for reg in active) + sum(item.checked_in_count or 0 for item in manual)
    )
    sources: dict[str, int] = {}
    for reg in active:
        source = reg.source or "direct"
        sources[source] = sources.get(source, 0) + 1 + (reg.guests or 0)
    for attendee in manual:
        source = attendee.source or "manual"
        sources[source] = sources.get(source, 0) + 1
    source_labels = {"direct": "Через бота", "manual": "Вручную", "social": "Другие соцсети"}
    source_lines = "\n".join(
        f"• {h(source_labels.get(source, source))}: {count}"
        for source, count in sorted(sources.items(), key=lambda item: -item[1])
    )
    average = sum(item.rating for item in feedback) / len(feedback) if feedback else 0
    text = (
        f"📊 <b>Аналитика: {h(show.title)}</b>\n\n"
        f"👥 Записано людей: {people} / {show.max_seats}\n"
        f"↩️ Отмен регистраций: {cancelled}\n"
        f"✅ Подтвердили: {confirmed}\n"
        f"🎟 Пришли: {arrived if show.checkin_enabled else 'режим входа выключен'}\n"
        f"⭐ Средняя оценка: {average:.1f} ({len(feedback)} ответов)\n\n"
        f"<b>Источники:</b>\n{source_lines or 'Нет данных'}"
    )
    await callback.message.answer(text)


@router.callback_query(AdminShowActionCb.filter(F.action == "tasks"))
async def show_tasks(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = [item for item in await crud.get_show_registrations(session, show.id) if not item.is_cancelled]
    manual = await crud.get_manual_attendees(session, show.id)
    pending_manual = sum(1 for item in manual if item.notification_confirmed_at is None)
    no_answer = sum(1 + (item.guests or 0) for item in regs if item.confirmed is None)
    occupied = sum(1 + (item.guests or 0) for item in regs) + len(manual)
    announced = await crud.has_any_announcement_been_sent(session, show.id)
    tasks = []
    if not announced:
        tasks.append("• 📣 Опубликовать анонс")
    if not show.registration_chat_id:
        tasks.append("• 🔔 Подключить рабочий канал записей")
    if pending_manual:
        tasks.append(f"• 💬 Уведомить вручную: {pending_manual}")
    if no_answer:
        tasks.append(f"• ❔ Не подтвердили участие: {no_answer}")
    if not tasks:
        tasks.append("• ✅ Срочных действий нет")
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Открыть записи", callback_data=AdminShowActionCb(action="regs", show_id=show.id).pack())
    if not show.registration_chat_id:
        builder.button(text="🔔 Подключить канал", callback_data=AdminShowActionCb(action="reg_chat", show_id=show.id).pack())
    if not announced:
        builder.button(text="📣 Продвижение", callback_data=AdminShowActionCb(action="promotion", show_id=show.id).pack())
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show.id).pack())
    builder.adjust(1)
    await callback.message.edit_text(
        f"🧭 <b>Задачи: {h(show.title)}</b>\n\n" + "\n".join(tasks) +
        f"\n\n🪑 Занято: {occupied} / {show.max_seats}",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "export"))
async def export_show_csv(callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    regs = await crud.get_show_registrations(session, show.id)
    manual = await crud.get_manual_attendees(session, show.id)
    feedback_by_user = {item.user_id: item for item in await crud.get_show_feedback(session, show.id)}
    output = io.StringIO()
    # Semicolon opens into columns in Excel installations with a Russian locale.
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Имя", "Telegram", "Доп. гости", "Статус записи", "Подтверждение", "Пришло фактически",
        "Источник", "Оценка", "Отзыв",
    ])
    source_labels = {
        "direct": "Прямая ссылка",
        "instagram": "Instagram",
        "channel": "Telegram-канал",
        "team": "Команда",
        "manual": "Добавлен вручную",
        "social": "Другие соцсети",
    }
    for reg in regs:
        item = feedback_by_user.get(reg.user_id)
        writer.writerow([
            _csv_cell(reg.attendee_name),
            _csv_cell(f"@{reg.user.username}" if reg.user.username else reg.user.telegram_id),
            reg.guests or 0,
            "Отменена" if reg.is_cancelled else "Активна",
            "Да" if reg.confirmed is True else "Нет" if reg.confirmed is False else "Не отвечал(а)",
            reg.checked_in_count or 0,
            _csv_cell(source_labels.get(reg.source or "direct", reg.source or "Прямая ссылка")),
            item.rating if item else "",
            _csv_cell(item.comment if item else ""),
        ])
    for attendee in manual:
        writer.writerow([
            _csv_cell(attendee.name), _csv_cell(attendee.contact or ""), 0, "Добавлен вручную", "Не требуется",
            attendee.checked_in_count or 0,
            _csv_cell(source_labels.get(attendee.source or "manual", attendee.source or "Добавлен вручную")), "", "",
        ])
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    await callback.message.answer_document(
        BufferedInputFile(data, filename=f"show-{show.id}-zriteli.csv"),
        caption=f"📥 Список зрителей по шоу «{h(show.title)}»",
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "add_manual"))
async def start_add_manual(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(AddManualFSM.names)
    await state.update_data(show_id=show_id, manual_source="manual")
    await callback.message.edit_text(
        "➕ <b>Добавить участников вручную</b>\n\n"
        "Отправь список — один зритель на строку. Контакт можно указать через <code>|</code>:\n\n"
        "<i>Иван Иванов | @ivan\nМария Петрова | instagram.com/maria\nАлексей Сидоров</i>"
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "chat_add_manual"))
async def start_add_manual_from_registration_chat(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    state: FSMContext,
    session: AsyncSession,
    is_super_admin: bool = False,
    db_user=None,
):
    """Start manual entry without replacing the notification in the working chat."""
    show = await crud.get_show(session, callback_data.show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return
    if callback.message.chat.id != show.registration_chat_id:
        await callback.answer("Эта кнопка работает только в чате записей.", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AddManualFSM.names)
    await state.update_data(
        show_id=show.id,
        manual_source="social",
        current_show_id=show.id,
    )
    await callback.message.answer(
        f"➕ <b>Добавить запись на «{h(show.title)}»</b>\n\n"
        "Отправь имена ответом на это сообщение — один зритель на строку. "
        "Контакт можно указать через <code>|</code>:\n\n"
        "<i>Иван Иванов | @ivan\nМария Петрова</i>"
    )


@router.message(AddManualFSM.names, F.text)
async def process_manual_names(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    show_id = data["show_id"]
    await state.clear()
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await message.answer("⛔ Нет доступа к этому шоу.")
        return

    rows = [line.strip() for line in message.text.splitlines() if line.strip()]
    parsed = [tuple(part.strip() for part in row.split("|", 1)) for row in rows]
    names = [parts[0] for parts in parsed if parts[0]]
    contacts = [parts[1] if len(parts) > 1 else None for parts in parsed if parts[0]]
    if not names:
        await message.answer("Список пустой, попробуй ещё раз.")
        return

    source = data.get("manual_source", "manual")
    count = await crud.add_manual_attendees(
        session, show_id, names, source=source, contacts=contacts,
    )
    if count == 0:
        occupied = await crud.count_active_registrations(session, show_id)
        await message.answer(
            f"😔 Нельзя добавить {len(names)}: свободно {max(0, show.max_seats - occupied)} мест."
        )
        return
    await message.answer(f"✅ Добавлено: {count} чел.")
    logger.info("added %s manual attendees to show_id=%s by admin=%s", count, show_id, message.from_user.id)
    await _render_registrations(message, show_id, session, edit=False, is_super_admin=is_super_admin, db_user=db_user)


@router.callback_query(AdminShowActionCb.filter(F.action == "del_manual"))
async def delete_manual_start(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if not _can_manage(is_super_admin, db_user, show.creator_id if show else None):
        await callback.answer("⛔ Нет доступа к этому шоу.", show_alert=True)
        return
    await callback.answer()

    manual = await crud.get_manual_attendees(session, show_id)

    if not manual:
        await callback.message.answer("Нет участников, добавленных вручную.")
        return

    lines = ["🗑 <b>Удаление вручную добавленных</b>\n"]
    for i, att in enumerate(manual, start=1):
        lines.append(f"{i}. {h(att.name)}")
    lines.append("\nВведи номера для удаления через пробел или запятую (например: <code>1 3 5</code> или <code>2-8</code>):")

    await state.set_state(DeleteManualFSM.select)
    await state.update_data(show_id=show_id, manual_ids=[att.id for att in manual])
    await callback.message.answer("\n".join(lines))


@router.message(DeleteManualFSM.select, F.text)
async def delete_manual_process(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    show_id = data["show_id"]
    manual_ids: list[int] = data["manual_ids"]
    await state.clear()

    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(message, "⛔ Нет доступа к этому шоу.")
        return

    indices: set[int] = set()
    for part in message.text.replace(",", " ").split():
        part = part.strip()
        if "-" in part:
            try:
                a, b = part.split("-", 1)
                indices.update(range(int(a), int(b) + 1))
            except ValueError:
                pass
        else:
            try:
                indices.add(int(part))
            except ValueError:
                pass

    to_delete = [manual_ids[i - 1] for i in sorted(indices) if 1 <= i <= len(manual_ids)]
    if not to_delete:
        await message.answer("Ничего не выбрано или неверные номера.")
        await _render_registrations(message, show_id, session, edit=False, is_super_admin=is_super_admin, db_user=db_user)
        return

    for att_id in to_delete:
        await crud.delete_manual_attendee(session, att_id)
    logger.info("deleted %s manual attendees from show_id=%s by admin=%s", len(to_delete), show_id, message.from_user.id)
    await message.answer(f"✅ Удалено: {len(to_delete)} чел.")
    await _render_registrations(
        message, show_id, session, edit=False,
        is_super_admin=is_super_admin, db_user=db_user,
    )
