from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta
from types import SimpleNamespace
from pathlib import Path

import pytest

from scheduler import jobs
from time_utils import utc_now


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _Connection:
    def __init__(self, acquired, *extra_results):
        self.acquired = acquired
        self.execute = AsyncMock(side_effect=[_ScalarResult(acquired), *extra_results])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Engine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


def test_scheduler_reconciles_immediately_and_every_fifteen_minutes(monkeypatch):
    fake_scheduler = MagicMock()
    monkeypatch.setattr(jobs, "scheduler", fake_scheduler)

    jobs.setup_scheduler(AsyncMock(), AsyncMock())

    announcement_job = fake_scheduler.add_job.call_args_list[0]
    trigger = announcement_job.args[1]
    assert trigger.interval.total_seconds() == 15 * 60
    assert announcement_job.kwargs["next_run_time"] is not None
    assert announcement_job.kwargs["coalesce"] is True
    assert announcement_job.kwargs["max_instances"] == 1
    fake_scheduler.start.assert_called_once_with()


@pytest.mark.asyncio
async def test_scheduler_skips_when_other_replica_holds_lock(monkeypatch):
    connection = _Connection(acquired=False)
    run_check = AsyncMock()
    monkeypatch.setattr(jobs, "is_sqlite", False)
    monkeypatch.setattr(jobs, "engine", _Engine(connection))
    monkeypatch.setattr(jobs, "_run_announcement_check", run_check)

    await jobs.check_and_send_announcements(AsyncMock(), AsyncMock())

    run_check.assert_not_awaited()
    connection.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_sqlite_runs_without_postgres_lock(monkeypatch):
    run_check = AsyncMock()
    monkeypatch.setattr(jobs, "is_sqlite", True)
    monkeypatch.setattr(jobs, "_run_announcement_check", run_check)

    public_bot = AsyncMock()
    admin_bot = AsyncMock()
    await jobs.check_and_send_announcements(public_bot, admin_bot)

    run_check.assert_awaited_once_with(public_bot, admin_bot)


@pytest.mark.asyncio
async def test_postgres_lock_is_released_after_success(monkeypatch):
    connection = _Connection(True, _ScalarResult(True))
    run_check = AsyncMock()
    monkeypatch.setattr(jobs, "is_sqlite", False)
    monkeypatch.setattr(jobs, "engine", _Engine(connection))
    monkeypatch.setattr(jobs, "_run_announcement_check", run_check)

    await jobs.check_and_send_announcements(AsyncMock(), AsyncMock())

    run_check.assert_awaited_once()
    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_postgres_lock_is_released_after_failure(monkeypatch):
    connection = _Connection(True, _ScalarResult(True))
    monkeypatch.setattr(jobs, "is_sqlite", False)
    monkeypatch.setattr(jobs, "engine", _Engine(connection))
    monkeypatch.setattr(jobs, "_run_announcement_check", AsyncMock(side_effect=RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="boom"):
        await jobs.check_and_send_announcements(AsyncMock(), AsyncMock())

    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_feedback_scheduler_skips_when_other_replica_holds_lock(monkeypatch):
    connection = _Connection(acquired=False)
    run_feedback = AsyncMock()
    monkeypatch.setattr(jobs, "is_sqlite", False)
    monkeypatch.setattr(jobs, "engine", _Engine(connection))
    monkeypatch.setattr(jobs, "_run_post_show_feedback", run_feedback)

    await jobs.request_post_show_feedback(AsyncMock())

    run_feedback.assert_not_awaited()
    connection.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_feedback_scheduler_releases_postgres_lock(monkeypatch):
    connection = _Connection(True, _ScalarResult(True))
    run_feedback = AsyncMock()
    monkeypatch.setattr(jobs, "is_sqlite", False)
    monkeypatch.setattr(jobs, "engine", _Engine(connection))
    monkeypatch.setattr(jobs, "_run_post_show_feedback", run_feedback)

    bot = AsyncMock()
    await jobs.request_post_show_feedback(bot)

    run_feedback.assert_awaited_once_with(bot)
    assert connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_channel_announcement_is_not_sent_twice(monkeypatch):
    show = SimpleNamespace(id=42, title="Show", poster_text=None, location="Venue", city="City",
                           location_url=None, registrar=None, registrar_username=None,
                           show_date=utc_now() + timedelta(days=1))
    already_sent = AsyncMock(side_effect=[False, True])
    send = AsyncMock(return_value=99)
    mark = AsyncMock()
    monkeypatch.setattr(jobs.crud, "has_announcement_been_sent", already_sent)
    monkeypatch.setattr(jobs, "send_to_channel", send)
    monkeypatch.setattr(jobs.crud, "mark_announcement_sent", mark)

    await jobs._maybe_send_channel(AsyncMock(), AsyncMock(), AsyncMock(), show, "1d")
    await jobs._maybe_send_channel(AsyncMock(), AsyncMock(), AsyncMock(), show, "1d")

    send.assert_awaited_once()
    mark.assert_awaited_once()


@pytest.mark.asyncio
async def test_reminders_mark_only_successful_deliveries(monkeypatch):
    show = SimpleNamespace(id=42, title="Show", show_date=utc_now() + timedelta(days=1),
                           location="Venue", city="City", location_url=None)
    good = SimpleNamespace(id=1, user=SimpleNamespace(telegram_id=100))
    blocked = SimpleNamespace(id=2, user=SimpleNamespace(telegram_id=200))
    monkeypatch.setattr(
        jobs.crud, "get_registrations_for_reminder",
        AsyncMock(side_effect=[[good, blocked], []]),
    )
    monkeypatch.setattr(jobs.crud, "get_last_channel_message_id", AsyncMock(return_value=None))
    mark = AsyncMock()
    monkeypatch.setattr(jobs.crud, "mark_reminded_many", mark)
    bot = AsyncMock()

    async def send_message(chat_id, *args, **kwargs):
        if chat_id == 200:
            raise RuntimeError("bot blocked")

    bot.send_message.side_effect = send_message
    await jobs._maybe_send_personal(AsyncMock(), bot, show, 1)

    assert mark.await_args.args[1] == [1]


@pytest.mark.asyncio
async def test_reconciliation_waits_for_configured_local_hour(monkeypatch):
    before_hour = datetime(2026, 8, 30, jobs.settings.REMINDER_HOUR_LOCAL - 1, 59)
    monkeypatch.setattr(jobs, "local_now", lambda: before_hour)
    list_shows = AsyncMock()
    monkeypatch.setattr(jobs.crud, "list_upcoming_shows", list_shows)

    await jobs._run_announcement_check(AsyncMock(), AsyncMock())

    list_shows.assert_not_awaited()


@pytest.mark.asyncio
async def test_downloaded_photo_is_deleted_after_success_and_failure():
    bot = AsyncMock()
    bot.get_file.return_value = SimpleNamespace(file_path="poster.jpg")

    async def download_file(file_path, destination):
        Path(destination).write_bytes(b"poster")

    bot.download_file.side_effect = download_file
    saved_path = None
    async with jobs._download_photo(bot, "file-id") as photo:
        saved_path = Path(photo.path)
        assert saved_path.exists()
    assert not saved_path.exists()

    with pytest.raises(RuntimeError, match="download failed"):
        bot.download_file.side_effect = RuntimeError("download failed")
        async with jobs._download_photo(bot, "file-id"):
            pass


@pytest.mark.asyncio
async def test_feedback_job_pages_candidates_and_marks_only_successes(monkeypatch):
    class SessionContext:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(jobs, "AsyncSessionLocal", lambda: SessionContext())
    first = SimpleNamespace(
        id=1, show_id=10,
        user=SimpleNamespace(telegram_id=100),
        show=SimpleNamespace(title="First"),
    )
    blocked = SimpleNamespace(
        id=2, show_id=10,
        user=SimpleNamespace(telegram_id=200),
        show=SimpleNamespace(title="Second"),
    )
    candidates = AsyncMock(side_effect=[[first, blocked], []])
    mark = AsyncMock()
    monkeypatch.setattr(jobs.crud, "get_feedback_candidates", candidates)
    monkeypatch.setattr(jobs.crud, "mark_feedback_requested", mark)
    bot = AsyncMock()

    async def send_message(chat_id, *args, **kwargs):
        if chat_id == 200:
            raise RuntimeError("blocked")

    bot.send_message.side_effect = send_message
    await jobs._run_post_show_feedback(bot)

    assert candidates.await_args_list[1].kwargs["after_id"] == 2
    assert mark.await_args.args[1] == [1]


@pytest.mark.asyncio
async def test_cleanup_job_uses_configured_fsm_ttl(monkeypatch):
    from db.fsm_storage import SQLAlchemyStorage

    cleanup = AsyncMock(return_value=3)
    monkeypatch.setattr(SQLAlchemyStorage, "cleanup_stale", cleanup)
    await jobs.cleanup_stale_fsm()
    cleanup.assert_awaited_once_with(jobs.settings.FSM_TTL_DAYS)
