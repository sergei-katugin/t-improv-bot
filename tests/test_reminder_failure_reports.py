from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scheduler import jobs, reminder_failures
from time_utils import utc_now


def _registration(*, reported: bool = False, username: str | None = "viewer"):
    return SimpleNamespace(
        id=5,
        attendee_name="Зритель <тест>",
        reminder_failure_reported_1d=reported,
        user=SimpleNamespace(telegram_id=12345, username=username),
    )


def test_failure_report_state_is_scoped_to_reminder_day():
    registration = _registration(reported=True)

    assert not reminder_failures.needs_failure_report(registration, 1)
    assert reminder_failures.needs_failure_report(registration, 2)


@pytest.mark.asyncio
async def test_reminders_mark_only_successful_deliveries(monkeypatch):
    show = SimpleNamespace(
        id=42, title="Show", show_date=utc_now() + timedelta(days=1),
        location="Venue", city="City", location_url=None,
        registration_chat_id=-10042,
    )
    good = SimpleNamespace(
        id=1, attendee_name="Good", reminder_failure_reported_1d=False,
        user=SimpleNamespace(telegram_id=100, username="good"),
    )
    blocked = SimpleNamespace(
        id=2, attendee_name="Blocked", reminder_failure_reported_1d=False,
        user=SimpleNamespace(telegram_id=200, username="blocked"),
    )
    monkeypatch.setattr(
        jobs.crud, "get_registrations_for_reminder",
        AsyncMock(side_effect=[[good, blocked], []]),
    )
    monkeypatch.setattr(
        jobs.crud, "get_last_channel_message_id", AsyncMock(return_value=None),
    )
    mark = AsyncMock()
    mark_reported = AsyncMock()
    monkeypatch.setattr(jobs.crud, "mark_reminded_many", mark)
    monkeypatch.setattr(jobs.crud, "mark_reminder_failures_reported", mark_reported)
    bot = AsyncMock()
    admin_bot = AsyncMock()

    async def send_message(chat_id, *_args, **_kwargs):
        if chat_id == 200:
            raise RuntimeError("bot blocked")

    bot.send_message.side_effect = send_message
    await jobs._maybe_send_personal(AsyncMock(), bot, admin_bot, show, 1)

    assert mark.await_args.args[1] == [1]
    cancel_button = bot.send_message.await_args_list[0].kwargs[
        "reply_markup"
    ].inline_keyboard[0][0]
    assert cancel_button.callback_data == "pub_cancel:42"
    report = admin_bot.send_message.await_args.args[1]
    assert "Blocked" in report and "@blocked" in report
    assert "Good" not in report
    assert mark_reported.await_args.args[1] == [2]


@pytest.mark.asyncio
async def test_failure_report_is_sent_to_registration_chat_and_marked(monkeypatch):
    session = AsyncMock()
    bot = AsyncMock()
    show = SimpleNamespace(id=9, title="Шоу", registration_chat_id=-1009)
    registration = _registration()
    mark = AsyncMock()
    monkeypatch.setattr(
        reminder_failures.crud, "mark_reminder_failures_reported", mark,
    )

    await reminder_failures.report_failed_personal_reminders(
        session, bot, show, [registration], 1,
    )

    assert bot.send_message.await_args.args[0] == -1009
    text = bot.send_message.await_args.args[1]
    assert "@viewer" in text
    assert "Зритель &lt;тест&gt;" in text
    mark.assert_awaited_once_with(session, [5], 1)


@pytest.mark.asyncio
async def test_failure_report_without_username_uses_telegram_id(monkeypatch):
    session = AsyncMock()
    bot = AsyncMock()
    show = SimpleNamespace(id=9, title="Шоу", registration_chat_id=-1009)
    monkeypatch.setattr(
        reminder_failures.crud, "mark_reminder_failures_reported", AsyncMock(),
    )

    await reminder_failures.report_failed_personal_reminders(
        session, bot, show, [_registration(username=None)], 1,
    )

    text = bot.send_message.await_args.args[1]
    assert "tg://user?id=12345" in text
    assert "Telegram ID: <code>12345</code>" in text
