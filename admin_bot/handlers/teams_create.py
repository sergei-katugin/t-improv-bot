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

from admin_bot.handlers.teams_manage import AddTeamFSM
from admin_bot.handlers.teams_manage import EditTeamFSM
from admin_bot.handlers.teams_manage import _is_admin
from admin_bot.handlers.teams_manage import _render_teams_list
from admin_bot.handlers.teams_manage import _team_summary


@router.callback_query(F.data.in_({"admin_team_add", "admin_team_add_from_onboarding"}))
async def team_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddTeamFSM.name)
    await state.update_data(_from_show_fsm=False)
    await callback.message.answer("Введи название новой команды:", reply_markup=fsm_cancel_kb())


@router.callback_query(F.data == "team_create_from_fsm")
async def team_create_from_show_fsm(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddTeamFSM.name)
    await state.update_data(_from_show_fsm=True)
    await callback.message.edit_text(
        "Введи название новой команды.\n"
        "После создания вернёмся к выбору команды для шоу.",
        reply_markup=fsm_cancel_kb(),
    )


@router.callback_query(F.data == "team_fsm_cancel_create")
async def team_fsm_cancel_create(callback: CallbackQuery, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    """Cancel team creation — return to show FSM if came from there, else to teams list."""
    await callback.answer()
    data = await state.get_data()
    came_from_show_fsm: bool = data.get("_from_show_fsm", False)
    if came_from_show_fsm:
        from admin_bot.handlers.shows import CreateShowFSM, _progress
        await state.set_state(CreateShowFSM.team_name)
        await callback.message.edit_text(
            f"{_progress(1)}Выбери команду из списка или введи своё название:",
            reply_markup=team_kb(),
        )
    else:
        await state.clear()
        await _render_teams_list(callback.message, db_user, is_super_admin, session, edit=True)


@router.message(AddTeamFSM.name, F.text)
async def team_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(team_name=name)
    await state.set_state(AddTeamFSM.members)
    await message.answer(
        "Введи Telegram-ники участников через запятую (необязательно):\n\n"
        "Например: @user_one, @user_two",
        reply_markup=team_create_fsm_skip_kb(),
    )


@router.callback_query(F.data == "team_fsm_skip_members")
async def team_skip_members(callback: CallbackQuery, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    await callback.answer()
    await _finish_team_creation(
        callback.message, state, members=None,
        telegram_id=callback.from_user.id, db_user=db_user, is_super_admin=is_super_admin, session=session,
    )


@router.message(AddTeamFSM.members, F.text)
async def team_add_members(message: Message, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    usernames = normalize_telegram_username_list(message.text)
    if usernames is None or not usernames:
        await message.answer(
            "Неверный формат. Введи Telegram-ники через запятую, например: "
            "@user_one, @user_two",
            reply_markup=team_create_fsm_skip_kb(),
        )
        return
    members = serialize_telegram_usernames(usernames)
    await _finish_team_creation(
        message, state, members=members,
        telegram_id=message.from_user.id, db_user=db_user, is_super_admin=is_super_admin, session=session,
    )


@router.callback_query(AddTeamFSM.name, F.data == "fsm_back")
async def team_add_name_back(
    callback: CallbackQuery, state: FSMContext, db_user=None,
    is_super_admin: bool = False, session: AsyncSession = None,
):
    await callback.answer()
    data = await state.get_data()
    if data.get("_from_show_fsm"):
        from admin_bot.handlers.shows import CreateShowFSM, _progress
        await state.set_state(CreateShowFSM.team_name)
        await callback.message.edit_text(
            f"{_progress(1)}Выбери команду из списка или введи своё название:",
            reply_markup=team_kb(),
        )
        return

    await state.clear()
    await _render_teams_list(callback.message, db_user, is_super_admin, session, edit=True)


@router.callback_query(EditTeamFSM.new_value, F.data == "fsm_back")
async def team_edit_back(callback: CallbackQuery, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    await callback.answer()
    data = await state.get_data()
    await state.clear()
    team = await crud.get_team(session, data["team_id"])
    if team:
        can_manage = _is_admin(db_user, is_super_admin) or (
            db_user is not None and team.creator_id == db_user.id
        )
        await callback.message.edit_text(_team_summary(team), reply_markup=team_detail_kb(team, can_manage))
    else:
        await callback.message.edit_text("Команда не найдена.")


@router.callback_query(AddTeamFSM.members, F.data == "fsm_back")
async def team_add_back_to_name(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddTeamFSM.name)
    await callback.message.edit_text("Введи название новой команды:", reply_markup=fsm_cancel_kb())


async def _finish_team_creation(msg, state: FSMContext, members, telegram_id: int, db_user, is_super_admin: bool, session: AsyncSession):
    data = await state.get_data()
    name: str = data["team_name"]
    came_from_show_fsm: bool = data.get("_from_show_fsm", False)

    creator_id = db_user.id if db_user is not None else 0
    team = await crud.create_team(session, name=name, members=members, creator_id=creator_id)
    logger.info("created team id=%s name=%s creator_id=%s", team.id, team.name, creator_id)

    if came_from_show_fsm:
        from admin_bot.handlers.shows import CreateShowFSM, _progress
        await state.update_data(_from_show_fsm=None, team_name=None)
        await state.set_state(CreateShowFSM.team_name)
        teams = await crud.list_teams(session)
        await msg.answer(
            f"✅ Команда <b>{h(team.name)}</b> создана!\n\n"
            f"{_progress(1)}Выбери команду для шоу:",
            reply_markup=team_select_kb(teams),
        )
    else:
        await state.clear()
        if _is_admin(db_user, is_super_admin):
            teams = await crud.list_teams(session)
        else:
            teams = await crud.list_teams(session, user_id=db_user.id if db_user else None)
        await msg.answer(
            f"✅ Команда <b>{h(team.name)}</b> создана!\n\n👥 <b>Команды</b>:",
            reply_markup=teams_list_kb(teams),
        )
