from db.audit_model import AuditLog as SplitAuditLog
from db.model_types import UserRole as SplitUserRole
from db.models import AuditLog, FSMStorageRecord, UserRole
from db.fsm_model import FSMStorageRecord as SplitFSMStorageRecord
from admin_bot.keyboards.inline import show_detail_kb, team_detail_kb
from admin_bot.keyboards.inline_catalog import team_detail_kb as split_team_detail_kb
from admin_bot.keyboards.inline_shows import show_detail_kb as split_show_detail_kb
from main import build_webhook_app
from webhook_runtime import build_webhook_app as split_build_webhook_app
from scheduler.jobs import MAPS_RE, build_announcement_text
from scheduler.messages import MAPS_RE as split_maps_re
from scheduler.messages import build_announcement_text as split_build_announcement_text
from public_bot.handlers import registration
from public_bot.handlers.registration_flow import confirm_registration
from admin_bot.handlers import registrations as admin_registrations
from admin_bot.handlers.registrations_checkin import toggle_checkin
from admin_bot.handlers import teams
from admin_bot.handlers.teams_create import AddTeamFSM
from admin_bot.handlers import shows
from admin_bot.handlers.shows_shared import CreateShowFSM
import miniapp_api
from miniapp_routes import register_miniapp_routes


def test_model_facade_preserves_public_types():
    assert AuditLog is SplitAuditLog
    assert UserRole is SplitUserRole
    assert FSMStorageRecord is SplitFSMStorageRecord


def test_keyboard_facade_preserves_public_builders():
    assert show_detail_kb is split_show_detail_kb
    assert team_detail_kb is split_team_detail_kb


def test_main_preserves_webhook_runtime_api():
    assert build_webhook_app is split_build_webhook_app


def test_scheduler_preserves_message_builder_api():
    assert build_announcement_text is split_build_announcement_text
    assert MAPS_RE is split_maps_re


def test_registration_facade_assembles_all_subrouters():
    assert registration.confirm_registration is confirm_registration
    assert len(registration.router.sub_routers) == 4


def test_admin_registration_facade_assembles_all_subrouters():
    assert admin_registrations.toggle_checkin is toggle_checkin
    assert len(admin_registrations.router.sub_routers) == 5


def test_teams_facade_assembles_all_subrouters():
    assert teams.AddTeamFSM is AddTeamFSM
    assert len(teams.router.sub_routers) == 2


def test_shows_facade_assembles_all_subrouters():
    assert shows.CreateShowFSM is CreateShowFSM
    assert len(shows.router.sub_routers) == 12


def test_miniapp_facade_preserves_route_registration():
    assert miniapp_api.register_miniapp_routes is register_miniapp_routes
