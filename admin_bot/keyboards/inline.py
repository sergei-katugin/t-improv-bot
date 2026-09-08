"""Stable keyboard facade; builders are grouped by screen domain."""

from admin_bot.keyboards.inline_shows import _show_status_icon, shows_list_kb, shows_filter_kb, show_detail_kb, show_section_kb, edit_notification_mode_kb, checkin_kb, checkin_mode_kb, checkin_counter_kb, party_count_kb, show_created_kb, edit_show_fields_kb, registrations_kb, registration_chat_kb, confirm_kb, confirm_with_back_kb
from admin_bot.keyboards.inline_catalog import organizers_list_kb, fsm_cancel_kb, fsm_skip_cancel_kb, settings_kb, ad_channels_list_kb, roles_menu_kb, city_kb, venue_kb, venues_list_kb, venue_detail_kb, team_kb, team_select_kb, team_create_fsm_skip_kb, teams_list_kb, team_detail_kb
