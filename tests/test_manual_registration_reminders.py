from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin_bot.handlers import registrations_manual
from db.models import UserRole


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=77),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_manual_registration_can_start_in_private_admin_bot(monkeypatch):
    callback = SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    state = AsyncMock()
    show = SimpleNamespace(id=10, creator_id=5, title="Премьера")
    user = SimpleNamespace(id=5, role=UserRole.organizer)
    monkeypatch.setattr(registrations_manual.crud, "get_show", AsyncMock(return_value=show))

    await registrations_manual.start_add_manual_from_registration_chat(
        callback, SimpleNamespace(show_id=10), state, AsyncMock(), db_user=user,
    )

    callback.answer.assert_awaited_once_with()
    state.update_data.assert_awaited_once_with(
        show_id=10, manual_source="social", current_show_id=10,
    )
    assert "Добавить запись" in callback.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_manual_registration_start_rejects_foreign_show(monkeypatch):
    callback = SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(answer=AsyncMock()))
    show = SimpleNamespace(id=10, creator_id=5, title="Премьера")
    monkeypatch.setattr(registrations_manual.crud, "get_show", AsyncMock(return_value=show))

    await registrations_manual.start_add_manual_from_registration_chat(
        callback, SimpleNamespace(show_id=10), AsyncMock(), AsyncMock(),
        db_user=SimpleNamespace(id=8, role=UserRole.organizer),
    )

    callback.answer.assert_awaited_once_with("⛔ Нет доступа к этому шоу.", show_alert=True)
    callback.message.answer.assert_not_awaited()


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
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(registrations_manual.crud, "register_user_safe", register)
    monkeypatch.setattr(registrations_manual.crud, "add_manual_attendees", add_manual)
    monkeypatch.setattr(registrations_manual.crud, "count_active_registrations", AsyncMock(return_value=4))

    await registrations_manual.process_chat_manual_guests(
        message, state, session, bot, is_super_admin=True,
    )

    register.assert_awaited_once_with(
        session, 10, 42, "Алиса", 1,
        source="registration_chat",
    )
    add_manual.assert_not_awaited()
    assert "автоматические напоминания" in message.answer.await_args.args[0]
    bot.send_message.assert_not_awaited()


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
    show = SimpleNamespace(
        id=10, creator_id=5, title="Премьера", max_guests=3, max_seats=20,
        registration_chat_id=-100500,
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(registrations_manual.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(registrations_manual.crud, "get_user_by_username", AsyncMock(return_value=None))
    register = AsyncMock()
    add_manual = AsyncMock(return_value=1)
    monkeypatch.setattr(registrations_manual.crud, "register_user_safe", register)
    monkeypatch.setattr(registrations_manual.crud, "add_manual_attendees", add_manual)
    monkeypatch.setattr(registrations_manual.crud, "count_active_registrations", AsyncMock(return_value=7))

    await registrations_manual.process_chat_manual_guests(
        message, state, AsyncMock(), bot, is_super_admin=True,
    )

    register.assert_not_awaited()
    add_manual.assert_awaited_once()
    assert "попробую отправить напоминание автоматически" in message.answer.await_args.args[0]
    bot.send_message.assert_awaited_once()
    notification = bot.send_message.await_args
    assert notification.args[0] == -100500
    assert "Добавлена запись вручную" in notification.args[1]
    assert "Telegram: @bob" in notification.args[1]
    assert "при ошибке сообщим здесь" in notification.args[1]
    assert "7 / 20" in notification.args[1]
