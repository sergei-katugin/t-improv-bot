"""Stable Mini App API facade; handlers are grouped by domain."""

import sys
import types
from admin_bot.registration_notifications import notify_manual_registration
from miniapp_common import *
from miniapp_helpers import _audit_details, _json_body, _manageable_api_show, _occupied_expression, _optional_text, _record_audit, _registration_url, _require_admin, _required_text, _show_fields, _show_id, _show_payload
from miniapp_security import miniapp_auth_concurrency_middleware, MiniAppRateLimiter, _miniapp_rate_policy, miniapp_rate_limit_middleware, MiniAppAuthError, TelegramMiniAppUser, validate_telegram_init_data, _extract_init_data, miniapp_auth_middleware, miniapp_request_logging_middleware, miniapp_security_headers_middleware, _set_miniapp_security_headers
from miniapp_core import miniapp_me, miniapp_audit_log
from miniapp_shows import miniapp_shows, miniapp_show_detail, miniapp_attention
from miniapp_promotion import miniapp_announcement_preview, miniapp_promotion, miniapp_send_test_announcement, miniapp_publish, miniapp_show_qr, miniapp_clone_show, miniapp_cancel_show
from miniapp_analytics import miniapp_show_analytics, _csv_value, miniapp_export_show_csv
from miniapp_media import miniapp_upload_poster, miniapp_poster, miniapp_options, miniapp_access_users, miniapp_create_access_invite, miniapp_update_access_user
from miniapp_catalog import miniapp_create_team, miniapp_update_team, miniapp_delete_team, miniapp_create_venue, miniapp_update_venue, miniapp_delete_venue, miniapp_create_ad_channel, miniapp_toggle_ad_channel, miniapp_delete_ad_channel
from miniapp_show_write import miniapp_create_show, miniapp_update_show
from miniapp_tasks_chat import miniapp_show_tasks, miniapp_remind_viewers, _verified_registration_chat, miniapp_verify_registration_chat, miniapp_registration_chats, miniapp_registration_chat, miniapp_clear_registration_chat, miniapp_confirm_manual_notifications, miniapp_restore_show, miniapp_delete_show
from miniapp_attendees import miniapp_add_manual_attendee, miniapp_attendees, miniapp_update_registration, miniapp_cancel_registration
from miniapp_routes import miniapp_index, register_miniapp_routes

_IMPLEMENTATION_MODULES = ['miniapp_common', 'miniapp_helpers', 'miniapp_security', 'miniapp_core', 'miniapp_shows', 'miniapp_promotion', 'miniapp_analytics', 'miniapp_media', 'miniapp_catalog', 'miniapp_show_write', 'miniapp_tasks_chat', 'miniapp_attendees', 'miniapp_routes']

class _FacadeModule(types.ModuleType):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        for module_name in _IMPLEMENTATION_MODULES:
            module = sys.modules.get(module_name)
            if module is not None and hasattr(module, name):
                setattr(module, name, value)

sys.modules[__name__].__class__ = _FacadeModule
