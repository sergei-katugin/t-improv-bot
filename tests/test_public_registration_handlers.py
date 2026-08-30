from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from public_bot.handlers import registration
from time_utils import utc_now


def _callback() -> SimpleNamespace:
    return SimpleNamespace(
        answer=AsyncMock(),
        message=SimpleNamespace(
            photo=None,
            answer=AsyncMock(),
            edit_text=AsyncMock(),
            edit_reply_markup=AsyncMock(),
            answer_document=AsyncMock(),
        ),
    )


def _show(**overrides):
    values = dict(
        id=10, title="Show", show_date=utc_now() + timedelta(days=1),
        is_active=True, max_seats=10, registration_chat_id=None,
        registration_chat_name_mode="short", registrar=None,
        registrar_username=None, poster_text=None, location="Venue", city="City",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_start_registration_rejects_missing_existing_and_full_show(monkeypatch):
    callback = _callback()
    state = AsyncMock()
    user = SimpleNamespace(id=1, first_name="Viewer")
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=None))
    await registration.start_registration(callback, SimpleNamespace(show_id=10), state, user, AsyncMock())
    callback.message.answer.assert_awaited_once_with("Шоу не найдено.")

    callback = _callback()
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=_show()))
    monkeypatch.setattr(registration.crud, "count_active_registrations", AsyncMock(return_value=1))
    monkeypatch.setattr(
        registration.crud, "get_registration",
        AsyncMock(return_value=SimpleNamespace(is_cancelled=False)),
    )
    await registration.start_registration(callback, SimpleNamespace(show_id=10), state, user, AsyncMock())
    assert "уже записан" in callback.answer.await_args.args[0]

    callback = _callback()
    monkeypatch.setattr(registration.crud, "count_active_registrations", AsyncMock(return_value=10))
    monkeypatch.setattr(registration.crud, "get_registration", AsyncMock(return_value=None))
    await registration.start_registration(callback, SimpleNamespace(show_id=10), state, user, AsyncMock())
    assert "все места" in callback.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_start_registration_populates_fsm_and_processes_name(monkeypatch):
    callback = _callback()
    state = AsyncMock()
    state.get_data.return_value = {"registration_source_show_id": 10, "registration_source": "ig"}
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=_show()))
    monkeypatch.setattr(registration.crud, "count_active_registrations", AsyncMock(return_value=0))
    monkeypatch.setattr(registration.crud, "get_registration", AsyncMock(return_value=None))

    await registration.start_registration(
        callback, SimpleNamespace(show_id=10), state,
        SimpleNamespace(id=1, first_name="Viewer"), AsyncMock(),
    )
    assert state.update_data.await_args.kwargs["registration_source"] == "ig"
    callback.message.edit_text.assert_awaited_once()

    message = SimpleNamespace(text="A", answer=AsyncMock())
    await registration.process_name(message, state)
    assert "от 2 до 100" in message.answer.await_args.args[0]

    state.reset_mock()
    state.get_data.return_value = {
        "show_id": 10, "show_title": "Show", "show_date": "01.01.2027",
    }
    message = SimpleNamespace(text=" Alice ", answer=AsyncMock())
    await registration.process_name(message, state)
    state.update_data.assert_awaited_once_with(attendee_name="Alice")
    assert state.set_state.await_args.args[0] == registration.RegisterFSM.choose_guests


@pytest.mark.asyncio
async def test_choose_guests_rejects_invalid_and_stale_then_confirms():
    state = AsyncMock()
    callback = _callback()
    await registration.choose_guests(callback, SimpleNamespace(show_id=10, guests=51), state)
    assert "Некорректное" in callback.answer.await_args.args[0]

    callback = _callback()
    state.get_data.return_value = {"show_id": 99}
    await registration.choose_guests(callback, SimpleNamespace(show_id=10, guests=1), state)
    assert "устарела" in callback.answer.await_args.args[0]

    callback = _callback()
    state.get_data.return_value = {
        "show_id": 10, "attendee_name": "Alice", "show_title": "Show",
        "show_date": "01.01.2027", "registration_chat_name_mode": "short",
    }
    await registration.choose_guests(callback, SimpleNamespace(show_id=10, guests=2), state)
    state.update_data.assert_awaited_with(guests=2)
    assert "+2 гостя" in callback.message.edit_text.await_args.args[0]


@pytest.mark.asyncio
async def test_confirm_registration_handles_stale_capacity_and_success(monkeypatch):
    user = SimpleNamespace(id=1)
    admin_bot = AsyncMock()
    state = AsyncMock()
    callback = _callback()
    state.get_data.return_value = {}
    await registration.confirm_registration(
        callback, SimpleNamespace(show_id=10), state, user, AsyncMock(), admin_bot,
    )
    assert "устарела" in callback.answer.await_args.args[0]

    data = {
        "show_id": 10, "attendee_name": "Alice", "show_title": "Show",
        "show_date": "01.01.2027", "guests": 2, "registration_source": "ig",
    }
    state.get_data.return_value = data
    callback = _callback()
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=_show()))
    monkeypatch.setattr(registration.crud, "register_user_safe", AsyncMock(return_value=None))
    monkeypatch.setattr(registration.crud, "count_active_registrations", AsyncMock(return_value=9))
    await registration.confirm_registration(
        callback, SimpleNamespace(show_id=10), state, user, AsyncMock(), admin_bot,
    )
    assert "Мест не хватает" in callback.message.edit_text.await_args.args[0]

    callback = _callback()
    monkeypatch.setattr(
        registration.crud, "register_user_safe", AsyncMock(return_value=SimpleNamespace(id=77)),
    )
    notify = AsyncMock()
    monkeypatch.setattr(registration, "_notify_registration_chat", notify)
    await registration.confirm_registration(
        callback, SimpleNamespace(show_id=10), state, user, AsyncMock(), admin_bot,
    )
    assert "Ты записан" in callback.message.answer.await_args.args[0]
    notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_feedback_rating_and_comment_validation(monkeypatch):
    callback = _callback()
    state = AsyncMock()
    user = SimpleNamespace(id=1)
    await registration.submit_feedback_rating(
        callback, SimpleNamespace(show_id=10, rating=9), state, user, AsyncMock(),
    )
    assert "Некорректная" in callback.answer.await_args.args[0]

    monkeypatch.setattr(registration.crud, "can_submit_feedback", AsyncMock(return_value=True))
    save = AsyncMock()
    monkeypatch.setattr(registration.crud, "save_feedback", save)
    callback = _callback()
    await registration.submit_feedback_rating(
        callback, SimpleNamespace(show_id=10, rating=5), state, user, AsyncMock(),
    )
    save.assert_awaited_once()
    assert state.set_state.await_args.args[0] == registration.RegisterFSM.feedback_comment

    state.get_data.return_value = {"feedback_show_id": 10, "feedback_rating": 5}
    message = SimpleNamespace(text="x" * 1200, answer=AsyncMock())
    await registration.submit_feedback_comment(message, state, user, AsyncMock())
    assert len(save.await_args.args[4]) == 1000


@pytest.mark.asyncio
async def test_calendar_download_handles_missing_and_builds_ics(monkeypatch):
    callback = _callback()
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=None))
    await registration.download_calendar_event(callback, SimpleNamespace(show_id=10), AsyncMock())
    assert "не найдено" in callback.answer.await_args.args[0]

    callback = _callback()
    monkeypatch.setattr(registration.crud, "get_show", AsyncMock(return_value=_show()))
    await registration.download_calendar_event(callback, SimpleNamespace(show_id=10), AsyncMock())
    document = callback.message.answer_document.await_args.args[0]
    assert document.filename == "show-10.ics"
