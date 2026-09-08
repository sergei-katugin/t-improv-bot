"""Team administration assembled from focused subrouters."""

from aiogram import Router
from db import crud
from admin_bot.handlers.teams_manage import router as manage_router, AddTeamFSM, EditTeamFSM, _team_summary, _is_admin, _render_teams_list, teams_list_entry, team_detail, team_field_action, team_save_field, team_confirm_delete
from admin_bot.handlers.teams_create import router as create_router, team_add_start, team_create_from_show_fsm, team_fsm_cancel_create, team_add_name, team_skip_members, team_add_members, team_add_name_back, team_edit_back, team_add_back_to_name, _finish_team_creation

router = Router()
router.include_router(manage_router)
router.include_router(create_router)
