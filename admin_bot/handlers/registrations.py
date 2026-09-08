"""Registration administration assembled from focused subrouters."""

from aiogram import Router
from db import crud
from admin_bot.handlers.registrations_entry import router as entry_router, _can_manage, registration_chat_membership_updated, remember_current_registration_chat, _csv_cell, AddManualFSM, DeleteManualFSM, RegistrationChatFSM, CheckinSearchFSM, _current_show_from_state, quick_registration_chat, skip_registration_chat, quick_checkin_mode
from admin_bot.handlers.registrations_chat import router as chat_router, _render_registrations, show_registrations, configure_registration_chat, _save_registration_chat, save_shared_registration_chat, save_registration_chat, clear_registration_chat, change_registration_chat_name_mode, confirm_manual_notifications
from admin_bot.handlers.registrations_checkin import router as checkin_router, _render_checkin, create_checkin_staff_invite, show_checkin, show_named_checkin, start_checkin_search, find_checkin_attendee, _notify_checkin_milestones, _named_arrived_total, toggle_checkin, toggle_manual_checkin, set_party_checkin, counter_checkin
from admin_bot.handlers.registrations_analytics import router as analytics_router, show_analytics, show_tasks, export_show_csv
from admin_bot.handlers.registrations_manual import router as manual_router, start_add_manual_from_registration_chat, process_chat_manual_name, process_chat_manual_source, process_chat_manual_contact, process_chat_manual_guests, delete_manual_start, delete_manual_process

router = Router()
router.include_router(entry_router)
router.include_router(chat_router)
router.include_router(checkin_router)
router.include_router(analytics_router)
router.include_router(manual_router)
