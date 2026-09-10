from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin_bot.handlers import registrations_manual


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=77),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_telegram_contact_is_normalized_and_saved_for_user_lookup():
    state = AsyncMock()
    state.get_data.return_value = {"manual_contact_source": "telegram"}
    message = _message(" https://t.me/Alice_123/ ")

    await registrations_manual.process_chat_manual_contact(message, state)

    state.update_data.assert_awaited_once_with(
        manual_contact="Telegram: @alice_123",
        manual_telegram_username="alice_123",
    )
    state.set_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_known_telegram_user_gets_regular_registration_and_reminders(monkeypatch):
    state = AsyncMock()
    state.get_data.return_value = {
        "show_id": 10,
        "manual_name": "Алиса",
        "manual_contact_source": "telegram",
        "manual_contact": "Telegram: @alice",
        "manual_telegram_username": "alice",
    }
    message = _message("1")
    show = SimpleNamespace(id=10, creator_id=5, max_guests=3, max_seats=20)
    user = SimpleNamespace(id=42)
    registration = SimpleNamespace(id=100)
    session = AsyncMock()
    monkeypatch.setattr(registrations_manual.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(registrations_manual.crud, "get_user_by_username", AsyncMock(return_value=user))
    register = AsyncMock(return_value=registration)
    add_manual = AsyncMock()
    monkeypatch.setattr(registrations_manual.crud, "register_user_safe", register)
    monkeypatch.setattr(registrations_manual.crud, "add_manual_attendees", add_manual)

    await registrations_manual.process_chat_manual_guests(
        message, state, session, is_super_admin=True,
    )

    register.assert_awaited_once_with(
        session, 10, 42, "Алиса", 1,
        source="registration_chat",
    )
    add_manual.assert_not_awaited()
    assert "автоматические напоминания" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_unknown_telegram_user_stays_manual_and_gets_chat_task(monkeypatch):
    state = AsyncMock()
    state.get_data.return_value = {
        "show_id": 10,
        "manual_name": "Боб",
        "manual_contact_source": "telegram",
        "manual_contact": "Telegram: @bob",
        "manual_telegram_username": "bob",
    }
    message = _message("0")
    show = SimpleNamespace(id=10, creator_id=5, max_guests=3, max_seats=20)
    monkeypatch.setattr(registrations_manual.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(registrations_manual.crud, "get_user_by_username", AsyncMock(return_value=None))
    register = AsyncMock()
    add_manual = AsyncMock(return_value=1)
    monkeypatch.setattr(registrations_manual.crud, "register_user_safe", register)
    monkeypatch.setattr(registrations_manual.crud, "add_manual_attendees", add_manual)

    await registrations_manual.process_chat_manual_guests(
        message, state, AsyncMock(), is_super_admin=True,
    )

    register.assert_not_awaited()
    add_manual.assert_awaited_once()
    assert "уведомить вручную" in message.answer.await_args.args[0]
