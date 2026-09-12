"""Shared arrival totals and threshold reports for the bots and Mini App."""
from sqlalchemy import func, select
from db import crud
from db.models import Registration, ManualAttendee
from html_utils import h
from app_logging import get_project_logger

logger = get_project_logger(__name__)


async def arrival_stats(session, show):
    booked = await crud.count_active_registrations(session, show.id)
    named = int(await session.scalar(select(func.coalesce(func.sum(Registration.checked_in_count), 0)).where(
        Registration.show_id == show.id, Registration.is_cancelled == False,
    )) or 0) + int(await session.scalar(select(func.coalesce(func.sum(ManualAttendee.checked_in_count), 0)).where(
        ManualAttendee.show_id == show.id,
    )) or 0)
    unidentified = show.checkin_counter or 0
    arrived = named + unidentified
    return {"arrived": arrived, "identified": named, "unidentified": unidentified, "booked": booked, "remaining": max(0, booked - arrived),
            "percent": round(arrived * 100 / booked, 1) if booked else 0}


async def notify_arrivals(bot, session, show, stats):
    claim = await crud.claim_checkin_milestones(session, show.id, stats["arrived"])
    if claim is None:
        return
    previous, highest, chat_id, title = claim
    try:
        await bot.send_message(chat_id,
            f"🎟 На шоу «{h(title)}» пришли и ждут начала уже <b>{stats['arrived']}</b> человек.\n"
            f"Записано: <b>{stats['booked']}</b> · Пришло: <b>{stats['percent']}%</b>\n"
            f"Ещё не пришли: <b>{stats['remaining']}</b>.")
    except Exception:
        await crud.release_checkin_milestones(session, show.id, highest, previous)
        logger.exception("Arrival report failed show_id=%s", show.id)
