from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin_bot.handlers import shows
from admin_bot.handlers import shows_entry


def _message(text: str | None = None):
    return SimpleNamespace(text=text, answer=AsyncMock(), photo=[], bot=AsyncMock())


def _callback():
    return SimpleNamespace(answer=AsyncMock(), message=SimpleNamespace(edit_text=AsyncMock(), answer=AsyncMock()))


@pytest.mark.asyncio
async def test_basic_navigation_clears_state_and_answers(monkeypatch):
    state = AsyncMock()
    message = _message()
    await shows.cmd_home(message, state)
    await shows.quick_home(message, state)
    state.get_state.return_value = "active"
    await shows.quick_cancel(message, state)
    assert state.clear.await_count == 3
    assert "отменено" in message.answer.await_args.args[0]

    state.get_state.return_value = None
    await shows.quick_cancel(message, state)
    assert "нет активного" in message.answer.await_args.args[0]

    monkeypatch.setattr(shows_entry, "miniapp_launch_kb", lambda: None)
    await shows.cmd_miniapp(message, state)
    assert "не настроен" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_manual_venue_city_seats_and_poster_steps():
    state = AsyncMock()
    state.get_data.return_value = {"_total": 10}

    message = _message(" Custom venue ")
    await shows.process_location(message, state)
    state.update_data.assert_awaited_with(location="Custom venue")

    callback = _callback()
    await shows.skip_location_url(callback, state)
    state.update_data.assert_awaited_with(location_url=None)

    invalid_url = _message("https://example.com")
    await shows.process_location_url(invalid_url, state)
    assert "не ссылка" in invalid_url.answer.await_args.args[0]
    valid_url = _message("https://maps.app.goo.gl/venue")
    await shows.process_location_url(valid_url, state)
    state.update_data.assert_awaited_with(location_url="https://maps.app.goo.gl/venue")

    custom_city = _callback()
    await shows.process_city_select(custom_city, SimpleNamespace(value="custom"), state)
    fixed_city = _callback()
    await shows.process_city_select(fixed_city, SimpleNamespace(value="Лимасол"), state)
    state.update_data.assert_awaited_with(city="Лимасол")
    await shows.process_city(_message(" Пафос "), state)
    state.update_data.assert_awaited_with(city="Пафос")

    invalid_seats = _message("zero")
    await shows.process_max_seats(invalid_seats, state)
    assert "корректное число" in invalid_seats.answer.await_args.args[0]
    await shows.process_max_seats(_message("80"), state)
    state.update_data.assert_awaited_with(max_seats=80)

    await shows.skip_poster_text(callback, state)
    state.update_data.assert_awaited_with(poster_text=None)
    invalid_poster = _message("Шоу в 19:00")
    await shows.process_poster_text(invalid_poster, state)
    assert "время" in invalid_poster.answer.await_args.args[0]
    await shows.process_poster_text(_message("Хорошее описание"), state)
    state.update_data.assert_awaited_with(poster_text="Хорошее описание")
    await shows.process_poster_text_fallback(_message(None), state)
    text_message = _message("already text")
    await shows.process_poster_text_fallback(text_message, state)
    text_message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_team_venue_and_time_choice_branches(monkeypatch):
    state = AsyncMock()
    session = AsyncMock()
    callback = _callback()

    monkeypatch.setattr(shows.crud, "list_teams", AsyncMock(return_value=[]))
    await shows.team_show_existing(callback, state, session)
    assert callback.answer.await_count == 2
    await shows.team_back_to_entry(callback, state)

    await shows.process_team_select(callback, SimpleNamespace(team_id=0), state, session)
    state.update_data.assert_awaited_with(team_id=None, _team_manual=True)
    monkeypatch.setattr(shows.crud, "get_team", AsyncMock(return_value=None))
    await shows.process_team_select(callback, SimpleNamespace(team_id=99), state, session)
    team = SimpleNamespace(id=1, name="Team")
    monkeypatch.setattr(shows.crud, "get_team", AsyncMock(return_value=team))
    await shows.process_team_select(callback, SimpleNamespace(team_id=1), state, session)
    state.update_data.assert_awaited_with(team_name="Team", team_id=1, _team_manual=False)

    state.get_data.return_value = {"_team_manual": False}
    monkeypatch.setattr(shows.crud, "list_teams", AsyncMock(return_value=[team]))
    await shows.process_team_name_manual(_message("Typed"), state, session)
    state.get_data.return_value = {"_team_manual": True}
    await shows.process_team_name_manual(_message("x"), state, session)
    await shows.process_team_name_manual(_message("Typed team"), state, session)

    await shows.process_venue_select(callback, SimpleNamespace(venue_id=0), state, session)
    monkeypatch.setattr(shows.crud, "get_venue", AsyncMock(return_value=None))
    await shows.process_venue_select(callback, SimpleNamespace(venue_id=9), state, session)
    venue = SimpleNamespace(id=2, name="Venue", maps_url="https://maps.example", city="City", default_seats=50)
    monkeypatch.setattr(shows.crud, "get_venue", AsyncMock(return_value=venue))
    await shows.process_venue_select(callback, SimpleNamespace(venue_id=2), state, session)
    assert state.update_data.await_args.kwargs["max_seats"] == 50

    await shows.process_time_custom(callback, state)
    bad_time = _message("bad")
    await shows.process_time(bad_time, state, session)
    assert "Неверный формат" in bad_time.answer.await_args.args[0]
