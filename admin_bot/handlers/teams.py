from aiogram import Router, F
import logging
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import UserRole
from admin_bot.callbacks import AdminTeamActionCb, AdminTeamFieldCb
from admin_bot.keyboards.inline import (
    teams_list_kb, team_detail_kb, team_kb, team_select_kb, confirm_kb,
    fsm_cancel_kb, team_create_fsm_skip_kb,
)

router = Router()

logger = logging.getLogger("t_improv_bot.admin.teams")


class AddTeamFSM(StatesGroup):
    name = State()
    members = State()


class EditTeamFSM(StatesGroup):
    new_value = State()


def _team_summary(team) -> str:
    members = team.members or "не указаны"
    status = "активна" if team.is_active else "скрыта"
    return (
        f"🎭 <b>{team.name}</b>\n"
        f"👥 Участники: {members}\n"
        f"Статус: {status}"
    )


def _is_admin(db_user, is_super_admin: bool) -> bool:
    if is_super_admin:
        return True
    return db_user is not None and db_user.role == UserRole.admin


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


# ── Entry points ──────────────────────────────────────────────────────────────

@router.message(F.text == "👥 Команды")
@router.message(Command("teams"))
@router.callback_query(F.data == "admin_teams_list")
async def teams_list_entry(event, state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await _render_teams_list(msg, db_user, is_super_admin, session, edit=isinstance(event, CallbackQuery))


# ── Team detail ───────────────────────────────────────────────────────────────

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
    can_manage = _is_admin(db_user, is_super_admin) or (
        db_user is not None and team.creator_id == db_user.id
    )
    await callback.message.edit_text(
        _team_summary(team), reply_markup=team_detail_kb(team, can_manage)
    )


# ── Edit field ────────────────────────────────────────────────────────────────

@router.callback_query(AdminTeamFieldCb.filter())
async def team_field_action(
    callback: CallbackQuery, callback_data: AdminTeamFieldCb,
    state: FSMContext, db_user=None, is_super_admin: bool = False, session: AsyncSession = None,
):
    await callback.answer()
    team_id = callback_data.team_id
    field = callback_data.field

    if field == "toggle":
        team = await crud.get_team(session, team_id)
        if team:
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
        "members": "Введи новый список участников (или «-» чтобы убрать):",
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

    value = None if (field == "members" and raw == "-") else raw
    team = await crud.update_team(session, team_id, **{field: value})

    await state.clear()
    can_manage = _is_admin(db_user, is_super_admin) or (
        db_user is not None and team.creator_id == db_user.id
    )
    await message.answer(_team_summary(team), reply_markup=team_detail_kb(team, can_manage))


# ── Confirm delete ─────────────────────────────────────────────────────────────

@router.callback_query(AdminTeamActionCb.filter(F.action == "confirm_delete"))
async def team_confirm_delete(callback: CallbackQuery, callback_data: AdminTeamActionCb, db_user=None, is_super_admin: bool = False, session: AsyncSession = None):
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


# ── Add team (from management screen or onboarding) ───────────────────────────

@router.callback_query(F.data.in_({"admin_team_add", "admin_team_add_from_onboarding"}))
async def team_add_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AddTeamFSM.name)
    await state.update_data(_from_show_fsm=False)
    await callback.message.answer("Введи название новой команды:", reply_markup=fsm_cancel_kb())


# ── Add team from show creation FSM ───────────────────────────────────────────

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


# ── Shared FSM steps for team creation ────────────────────────────────────────

@router.message(AddTeamFSM.name, F.text)
async def team_add_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(team_name=name)
    await state.set_state(AddTeamFSM.members)
    await message.answer(
        "Введи список участников через запятую (необязательно):",
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
    members = message.text.strip() or None
    await _finish_team_creation(
        message, state, members=members,
        telegram_id=message.from_user.id, db_user=db_user, is_super_admin=is_super_admin, session=session,
    )


# ── FSM back handlers ─────────────────────────────────────────────────────────

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
            f"✅ Команда <b>{team.name}</b> создана!\n\n"
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
            f"✅ Команда <b>{team.name}</b> создана!\n\n👥 <b>Команды</b>:",
            reply_markup=teams_list_kb(teams),
        )
