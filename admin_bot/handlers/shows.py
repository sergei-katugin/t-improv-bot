"""Show administration assembled from focused subrouters."""

from aiogram import Router
from admin_bot.handlers.shows_shared import *
from admin_bot.handlers.shows_entry import router as entry_router, cmd_start, cmd_miniapp, cmd_home, quick_home, quick_cancel, _quick_show, quick_show_registrations, quick_show_promotion, quick_back_to_show, quick_promotion_preview, quick_promotion_announce, quick_promotion_link, quick_show_edit, quick_back_to_shows, cmd_create_show, cmd_shows_message, cmd_my_shows, cmd_settings, back_to_settings
from admin_bot.handlers.shows_create_team import router as create_team_router, team_show_existing, team_back_to_entry, process_team_select, process_team_name_manual, process_title, show_date_text_guard, process_calendar, _time_kb, process_time_preset, process_time_custom, process_time, _save_time
from admin_bot.handlers.shows_create_place import router as create_place_router, process_venue_select, process_location, skip_location_url, process_location_url, process_city_select, process_city, process_max_seats, skip_poster_text, process_poster_text, process_poster_text_fallback, skip_poster_image, process_poster_image, process_poster_image_invalid
from admin_bot.handlers.shows_create_confirm import router as create_confirm_router, _make_calendar, _preview_from_data, _show_confirm, toggle_create_option, _ask_registrar
from admin_bot.handlers.shows_create_finish import router as create_finish_router, fsm_back, fsm_cancel, process_registrar_choice, process_manual_registrar_input, confirm_create, cancel_create
from admin_bot.handlers.shows_listing import router as listing_router, _render_shows_list, cmd_shows_callback, shows_page, shows_filter_menu, filter_set_status, filter_reset, filter_set_team, filter_set_year, filter_input, show_detail, show_section
from admin_bot.handlers.shows_clone import router as clone_router, clone_show_start, clone_show_date, clone_show_time_preset, clone_show_custom_time, clone_show_time_text, _finish_clone_show, toggle_show_checkin, toggle_show_feedback
from admin_bot.handlers.shows_promotion import router as promotion_router, show_announcement_preview, _show_deep_link, _tracked_show_link, send_show_link, send_show_qr, send_manual_announcement, remind_viewers, free_ad
from admin_bot.handlers.shows_lifecycle import router as lifecycle_router, cancel_show_confirm, delete_show_confirm, delete_show_execute, cancel_show_execute, restore_show
from admin_bot.handlers.shows_edit_start import router as edit_start_router, start_edit, choose_edit_notification_mode, choose_edit_field
from admin_bot.handlers.shows_edit_fields import router as edit_fields_router, edit_team_select, edit_city_select, edit_venue_select, edit_date_text_guard, process_edit_calendar, process_edit_time_preset, process_edit_time_custom, process_edit_time, _save_edit_datetime
from admin_bot.handlers.shows_edit_finish import router as edit_finish_router, _ask_edit_registrar, edit_process_registrar_choice, save_edit_photo, save_edit_text, _apply_edit
from admin_bot.handlers.shows_notifications import _notify_show_change, _notify_date_change

router = Router()
router.include_router(entry_router)
router.include_router(create_team_router)
router.include_router(create_place_router)
router.include_router(create_confirm_router)
router.include_router(create_finish_router)
router.include_router(listing_router)
router.include_router(clone_router)
router.include_router(promotion_router)
router.include_router(lifecycle_router)
router.include_router(edit_start_router)
router.include_router(edit_fields_router)
router.include_router(edit_finish_router)
