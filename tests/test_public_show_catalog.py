from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest

from public_bot.handlers import shows


def _message(*, photo=False):
    return SimpleNamespace(
        photo=[object()] if photo else [], answer=AsyncMock(), edit_text=AsyncMock(),
    )


def _telegram_message(*, photo=False):
    message = Mock(spec=shows.Message)
    message.photo = [object()] if photo else []
    message.answer = AsyncMock()
    message.edit_text = AsyncMock()
    return message


def _callback(*, photo=False):
    return SimpleNamespace(answer=AsyncMock(), message=_message(photo=photo))


@pytest.mark.asyncio
async def test_cmd_shows_clears_state_and_opens_first_page(monkeypatch):
    event = _telegram_message()
    state = SimpleNamespace(clear=AsyncMock())
    render = AsyncMock()
    monkeypatch.setattr(shows, "_show_catalog_page", render)

    await shows.cmd_shows(event, state, SimpleNamespace(id=3), "session")

    state.clear.assert_awaited_once()
    event.answer.assert_not_awaited()
    render.assert_awaited_once_with(event, ANY, "session", page=0)


@pytest.mark.asyncio
async def test_paginate_clamps_negative_page(monkeypatch):
    callback = _callback()
    render = AsyncMock()
    monkeypatch.setattr(shows, "_show_catalog_page", render)

    await shows.paginate_shows(
        callback, SimpleNamespace(page=-4), SimpleNamespace(id=3), "session",
    )

    render.assert_awaited_once_with(callback, ANY, "session", page=0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event,method",
        [(_telegram_message(), "answer"), (_callback(), "edit_text"), (_callback(photo=True), "answer")],
)
async def test_empty_catalog_uses_a_method_suitable_for_message_type(monkeypatch, event, method):
    monkeypatch.setattr(shows.crud, "list_upcoming_shows", AsyncMock(return_value=[]))
    monkeypatch.setattr(shows.crud, "get_user_registrations", AsyncMock(return_value=[]))

    await shows._show_catalog_page(event, SimpleNamespace(id=3), "session", page=2)

    target = event if hasattr(event, "edit_text") else event.message
    getattr(target, method).assert_awaited_once_with("😔 Сейчас нет предстоящих шоу. Загляни позже!")


@pytest.mark.asyncio
async def test_catalog_builds_page_with_registration_ids_and_more_flag(monkeypatch):
    rows = [SimpleNamespace(id=index) for index in range(11)]
    callback = _callback()
    keyboard = object()
    builder = Mock(return_value=keyboard)
    list_shows = AsyncMock(return_value=rows)
    monkeypatch.setattr(shows.crud, "list_upcoming_shows", list_shows)
    monkeypatch.setattr(
        shows.crud, "get_user_registrations",
        AsyncMock(return_value=[SimpleNamespace(show_id=4)]),
    )
    monkeypatch.setattr(shows, "shows_list_kb", builder)

    await shows._show_catalog_page(callback, SimpleNamespace(id=3), "session", page=2)

    list_shows.assert_awaited_once_with("session", limit=11, offset=20)
    builder.assert_called_once_with(rows[:10], {4}, page=2, has_more=True)
    assert callback.message.edit_text.await_args.kwargs["reply_markup"] is keyboard


@pytest.mark.asyncio
async def test_show_detail_handles_missing_show(monkeypatch):
    callback = _callback()
    monkeypatch.setattr(shows.crud, "get_show", AsyncMock(return_value=None))

    await shows.show_detail(
        callback, SimpleNamespace(show_id=404), SimpleNamespace(id=3), "session",
    )

    callback.message.edit_text.assert_awaited_once_with("Шоу не найдено.")


@pytest.mark.asyncio
@pytest.mark.parametrize("photo,method", [(False, "edit_text"), (True, "answer")])
async def test_show_detail_renders_capacity_and_registration(monkeypatch, photo, method):
    callback = _callback(photo=photo)
    show = SimpleNamespace(id=7, max_seats=12)
    registration = SimpleNamespace(is_cancelled=False)
    keyboard = object()
    monkeypatch.setattr(shows.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(shows.crud, "count_active_registrations", AsyncMock(return_value=15))
    monkeypatch.setattr(shows.crud, "get_registration", AsyncMock(return_value=registration))
    monkeypatch.setattr(shows, "show_text", Mock(return_value="card"))
    keyboard_builder = Mock(return_value=keyboard)
    monkeypatch.setattr(shows, "show_detail_kb", keyboard_builder)

    await shows.show_detail(
        callback, SimpleNamespace(show_id=7), SimpleNamespace(id=3), "session",
    )

    keyboard_builder.assert_called_once_with(show, True, 0)
    call = getattr(callback.message, method).await_args
    assert call.args[0] == "card"
    assert call.kwargs["reply_markup"] is keyboard


@pytest.mark.asyncio
async def test_filter_start_falls_back_to_new_message_for_photo(monkeypatch):
    callback = _callback(photo=True)
    callback.message.edit_text.side_effect = TelegramBadRequest(
        method=Mock(), message="message has media",
    )
    state = SimpleNamespace(set_state=AsyncMock())

    await shows.filter_city_start(callback, state)

    state.set_state.assert_awaited_once_with(shows.FilterFSM.enter_city)
    callback.message.answer.assert_awaited_once_with("Введи название города:")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler,query,answer",
    [
        (shows.filter_by_city, "city", "Нет шоу в городе «&lt;Лимасол&gt;»."),
        (shows.filter_by_venue, "location", "Нет шоу на площадке «&lt;Сцена&gt;»."),
    ],
)
async def test_filters_escape_empty_search_values(monkeypatch, handler, query, answer):
    message = _message()
    message.text = "  <Лимасол>  " if query == "city" else "  <Сцена>  "
    state = SimpleNamespace(clear=AsyncMock())
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(shows.crud, "list_upcoming_shows", search)
    monkeypatch.setattr(shows.crud, "get_user_registrations", AsyncMock(return_value=[]))
    monkeypatch.setattr(shows, "shows_list_kb", Mock(return_value="keyboard"))

    await handler(message, state, SimpleNamespace(id=3), "session")

    search.assert_awaited_once_with("session", **{query: message.text.strip()})
    assert message.answer.await_args.args[0] == answer


@pytest.mark.asyncio
async def test_no_seats_uses_alert():
    callback = _callback()

    await shows.no_seats(callback)

    callback.answer.assert_awaited_once_with(
        "К сожалению, мест больше нет 😔", show_alert=True,
    )
