from unittest.mock import AsyncMock
from datetime import timedelta
from types import SimpleNamespace

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
