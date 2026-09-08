from datetime import datetime, timezone
from typing import Callable

from apscheduler.triggers.interval import IntervalTrigger

from config import settings


def configure_scheduler(
    scheduler,
    public_bot,
    admin_bot,
    *,
    announcement_job: Callable,
    feedback_job: Callable,
    chat_cleanup_job: Callable,
    fsm_cleanup_job: Callable,
) -> None:
    common = {"replace_existing": True, "coalesce": True, "max_instances": 1}
    scheduler.add_job(
        announcement_job,
        IntervalTrigger(minutes=15, timezone=settings.APP_TIMEZONE),
        args=[public_bot, admin_bot],
        id="daily_announcement_check",
        next_run_time=datetime.now(timezone.utc),
        **common,
    )
    scheduler.add_job(
        feedback_job,
        IntervalTrigger(hours=1, timezone=settings.APP_TIMEZONE),
        args=[public_bot],
        id="post_show_feedback",
        **common,
    )
    scheduler.add_job(
        chat_cleanup_job,
        IntervalTrigger(hours=1, timezone=settings.APP_TIMEZONE),
        args=[admin_bot],
        id="disconnect_finished_registration_chats",
        **common,
    )
    scheduler.add_job(
        fsm_cleanup_job,
        IntervalTrigger(hours=24, timezone=settings.APP_TIMEZONE),
        id="fsm_storage_cleanup",
        next_run_time=datetime.now(timezone.utc),
        **common,
    )
    scheduler.start()
