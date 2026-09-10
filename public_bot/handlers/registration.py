"""Registration router assembled from focused subrouters."""

from aiogram import Router
from admin_bot.callbacks import AdminShowActionCb
from db import crud
from public_bot.handlers.registration_entry import router as entry_router, registration_closed, join_show_waitlist, RegisterFSM, _guests_label, _registration_privacy_note, _notify_registration_chat, _notify_registration_cancellation
from public_bot.handlers.registration_flow import router as flow_router, start_registration, process_name, choose_guests, guests_custom, process_guests_count, process_edit_guests_count, confirm_registration
from public_bot.handlers.registration_feedback import router as feedback_router, _ics_escape, download_calendar_event, submit_feedback_rating, start_feedback_comment, cancel_feedback_comment, submit_feedback_comment
from public_bot.handlers.registration_attendance import router as attendance_router, toggle_reminder, handle_attendance, edit_guests_start, set_guests

router = Router()
router.include_router(entry_router)
router.include_router(flow_router)
router.include_router(feedback_router)
router.include_router(attendance_router)
