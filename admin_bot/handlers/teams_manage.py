from app_logging import get_project_logger
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from db import crud
from admin_bot.callbacks import AdminTeamActionCb, AdminTeamFieldCb
from admin_bot.keyboards.inline import teams_list_kb, team_detail_kb, team_kb, team_select_kb, confirm_kb, fsm_cancel_kb, team_create_fsm_skip_kb
from admin_bot.keyboards.reply import miniapp_launch_kb
from admin_bot.telegram_usernames import normalize_telegram_username_list, render_telegram_username_list, serialize_telegram_usernames
from admin_bot.security import can_manage_owned, deny, is_admin
from html_utils import h

router = Router()
logger = get_project_logger(__name__)



class AddTeamFSM(StatesGroup):
    name = State()
    members = State()


class EditTeamFSM(StatesGroup):
    new_value = State()


def _team_summary(team) -> str:
    members = render_telegram_username_list(team.members)
    status = "активна" if team.is_active else "скрыта"
    return (
        f"🎭 <b>{h(team.name)}</b>\n"
        f"👥 Участники: {members}\n"
        f"Статус: {status}"
    )


def _is_admin(db_user, is_super_admin: bool) -> bool:
    return is_admin(db_user, is_super_admin)


async def _render_teams_list(msg, db_user, is_super_admin: bool, session: AsyncSession, edit: bool = False):
    if _is_admin(db_user, is_super_admin):
        teams = await crud.list_teams(session)
    else:
        teams = await crud.list_teams(session, user_id=db_user.id if db_user else None)
    text = "👥 <b>Команды</b>\n\nВыбери команду для редактирования или создай новую:"
    if edit:
        await msg.edit_text(text, reply_markup=teams_list_kb(teams))
    else:
        await msg.answer(text, reply_markup=teams_list_kb(teams))


@router.message(F.text == "👥 Команды")
@router.message(Command("teams"))
@router.callback_query(F.data == "admin_teams_list")
async def teams_list_entry(event, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    text = "Команды создаются и редактируются в Mini App."
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=miniapp_launch_kb())
    else:
        await msg.edit_text(text, reply_markup=miniapp_launch_kb())


@router.callback_query(AdminTeamActionCb.filter(F.action == "open"))
async def team_detail(
    callback: CallbackQuery, callback_data: AdminTeamActionCb,
    state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None,
):
    await state.clear()
    await callback.answer()
    team = await crud.get_team(session, callback_data.team_id)
    if team is None:
        await callback.message.answer("Команда не найдена.")
        return
    if not can_manage_owned(team.creator_id, db_user, is_super_admin):
        await deny(callback)
        return
    can_manage = _is_admin(db_user, is_super_admin) or (
        db_user is not None and team.creator_id == db_user.id
    )
    await callback.message.edit_text(
        _team_summary(team), reply_markup=team_detail_kb(team, can_manage)
    )


@router.callback_query(AdminTeamFieldCb.filter())
async def team_field_action(
    callback: CallbackQuery, callback_data: AdminTeamFieldCb,
    state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None,
):
    await callback.answer()
    team_id = callback_data.team_id
    field = callback_data.field
    team = await crud.get_team(session, team_id)
    if team is None or not can_manage_owned(team.creator_id, db_user, is_super_admin):
        await deny(callback)
        return

    if field == "toggle":
        await crud.update_team(session, team_id, is_active=not team.is_active)
        team = await crud.get_team(session, team_id)
        can_manage = _is_admin(db_user, is_super_admin) or (
            db_user is not None and team.creator_id == db_user.id
        )
        await callback.message.edit_text(_team_summary(team), reply_markup=team_detail_kb(team, can_manage))
        return

    if field == "delete":
        await callback.message.edit_text(
            "Удалить команду? Это действие необратимо.",
            reply_markup=confirm_kb(
                AdminTeamActionCb(action="confirm_delete", team_id=team_id).pack(),
                AdminTeamActionCb(action="open", team_id=team_id).pack(),
            ),
        )
        return

    prompts = {
        "name":    "Введи новое название команды:",
        "members": (
            "Введи Telegram-ники участников через запятую "
            "(например: @user_one, @user_two) или «-» чтобы убрать:"
        ),
    }
    await state.set_state(EditTeamFSM.new_value)
    await state.update_data(team_id=team_id, field=field)
    await callback.message.edit_text(prompts[field], reply_markup=fsm_cancel_kb())


@router.message(EditTeamFSM.new_value, F.text)
async def team_save_field(message: Message, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    data = await state.get_data()
    team_id: int = data["team_id"]
    field: str = data["field"]
    raw = message.text.strip()

    current_team = await crud.get_team(session, team_id)
    if current_team is None or not can_manage_owned(current_team.creator_id, db_user, is_super_admin):
        await state.clear()
        await deny(message)
        return

    if field == "members":
        if raw == "-":
            value = None
        else:
            usernames = normalize_telegram_username_list(raw)
            if usernames is None or not usernames:
                await message.answer(
                    "Неверный формат. Введи Telegram-ники через запятую, например: "
                    "@user_one, @user_two"
                )
                return
            value = serialize_telegram_usernames(usernames)
    else:
        value = raw
    team = await crud.update_team(session, team_id, **{field: value})

    await state.clear()
    can_manage = _is_admin(db_user, is_super_admin) or (
        db_user is not None and team.creator_id == db_user.id
    )
    await message.answer(_team_summary(team), reply_markup=team_detail_kb(team, can_manage))


@router.callback_query(AdminTeamActionCb.filter(F.action == "confirm_delete"))
async def team_confirm_delete(callback: CallbackQuery, callback_data: AdminTeamActionCb, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    team = await crud.get_team(session, callback_data.team_id)
    if team is None or not can_manage_owned(team.creator_id, db_user, is_super_admin):
        await deny(callback)
        return
    await callback.answer()
    await crud.delete_team(session, callback_data.team_id)
    logger.info("deleted team id=%s by admin=%s", callback_data.team_id, callback.from_user.id)
    if _is_admin(db_user, is_super_admin):
        teams = await crud.list_teams(session)
    else:
        teams = await crud.list_teams(session, user_id=db_user.id if db_user else None)
    await callback.message.edit_text(
        "🗑 Команда удалена.\n\n👥 <b>Команды</b>:",
        reply_markup=teams_list_kb(teams),
    )
