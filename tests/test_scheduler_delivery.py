from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from scheduler import jobs
from time_utils import utc_now


def _show(**overrides):
    values = dict(
        id=8, poster_file_id=None, title="Шоу", poster_text="",
        team_name="Команда", show_date=utc_now(), location="Театр",
        location_url=None, city="Лимасол", registrar=None,
        registrar_username=None, max_seats=80,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_channel_delivery_text_photo_caption_and_long_text(monkeypatch):
    public = AsyncMock()
    admin = AsyncMock()
    public.send_message.return_value = SimpleNamespace(message_id=11)
    public.send_photo.return_value = SimpleNamespace(message_id=12)

    assert await jobs._send_to_channel_once(public, admin, _show(), "text", None, None) == 11
    public.send_message.assert_awaited_once()

    @asynccontextmanager
    async def photo(*_args):
        yield b"photo"

    monkeypatch.setattr(jobs, "_download_photo", photo)
    poster_show = _show(poster_file_id="file")
    assert await jobs._send_to_channel_once(public, admin, poster_show, "short", None, 4) == 12
    assert public.send_photo.await_args.kwargs["reply_to_message_id"] == 4

    public.send_message.reset_mock()
    assert await jobs._send_to_channel_once(public, admin, poster_show, "x" * 1025, None, None) == 11
    public.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_delivery_falls_back_when_photo_or_reply_fails(monkeypatch):
    public = AsyncMock()
    admin = AsyncMock()
    public.send_message.return_value = SimpleNamespace(message_id=21)

    @asynccontextmanager
    async def broken_photo(*_args):
        raise RuntimeError("download")
        yield

    monkeypatch.setattr(jobs, "_download_photo", broken_photo)
    assert await jobs._send_to_channel_once(public, admin, _show(poster_file_id="bad"), "text", None, None) == 21

    original = AsyncMock(side_effect=[
        TelegramBadRequest(method=SimpleNamespace(), message="message to be replied not found"),
        22,
    ])
    monkeypatch.setattr(jobs, "_send_to_channel_once", original)
    assert await jobs.send_to_channel(public, admin, _show(), "text", reply_to_message_id=99) == 22
    assert original.await_args_list[-1].args[-1] is None


@pytest.mark.asyncio
async def test_cache_poster_success_delete_failure_and_download_failure(monkeypatch):
    public = AsyncMock()
    admin = AsyncMock()
    public.send_photo.return_value = SimpleNamespace(
        message_id=33, photo=[SimpleNamespace(file_id="public-file")],
    )

    @asynccontextmanager
    async def photo(*_args):
        yield b"photo"

    monkeypatch.setattr(jobs, "_download_photo", photo)
    assert await jobs.cache_poster_for_public_bot(admin, public, "admin-file", 42) == "public-file"
    public.delete_message.side_effect = RuntimeError("cannot delete")
    assert await jobs.cache_poster_for_public_bot(admin, public, "admin-file", 42) == "public-file"

    @asynccontextmanager
    async def broken(*_args):
        raise RuntimeError("cannot download")
        yield

    monkeypatch.setattr(jobs, "_download_photo", broken)
    assert await jobs.cache_poster_for_public_bot(admin, public, "admin-file", 42) is None


@pytest.mark.asyncio
async def test_channel_announcement_claim_success_duplicate_and_failure(monkeypatch):
    session = AsyncMock()
    public = AsyncMock()
    admin = AsyncMock()
    show = _show()
    monkeypatch.setattr(jobs.crud, "has_announcement_been_sent", AsyncMock(return_value=True))
    send = AsyncMock(return_value=44)
    monkeypatch.setattr(jobs, "send_to_channel", send)
    await jobs._maybe_send_channel(session, public, admin, show, "1d")
    send.assert_not_awaited()

    monkeypatch.setattr(jobs.crud, "has_announcement_been_sent", AsyncMock(return_value=False))
    mark = AsyncMock()
    monkeypatch.setattr(jobs.crud, "mark_announcement_sent", mark)
    await jobs._maybe_send_channel(session, public, admin, show, "1d")
    mark.assert_awaited_once_with(session, 8, "1d", channel_message_id=44)

    send.side_effect = RuntimeError("telegram")
    await jobs._maybe_send_channel(session, public, admin, show, "2d")


@pytest.mark.asyncio
async def test_manual_attendee_reminder_success_and_creator_fallback(monkeypatch):
    session = AsyncMock()
    bot = AsyncMock()
    show = _show(registration_chat_id=-100, creator=SimpleNamespace(telegram_id=77))
    attendees = [SimpleNamespace(id=1, name="Анна", contact="@annie")]
    monkeypatch.setattr(jobs.crud, "get_pending_manual_attendees_for_reminder", AsyncMock(return_value=[]))
    await jobs._maybe_remind_manual_attendees(session, bot, show)
    bot.send_message.assert_not_awaited()

    monkeypatch.setattr(jobs.crud, "get_pending_manual_attendees_for_reminder", AsyncMock(return_value=attendees))
    monkeypatch.setattr(jobs.crud, "mark_manual_attendees_reminded", AsyncMock())
    await jobs._maybe_remind_manual_attendees(session, bot, show)
    jobs.crud.mark_manual_attendees_reminded.assert_awaited_once_with(session, [1])

    bot.send_message.reset_mock()
    bot.send_message.side_effect = [RuntimeError("chat"), None]
    await jobs._maybe_remind_manual_attendees(session, bot, show)
    assert bot.send_message.await_count == 2
