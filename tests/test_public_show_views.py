from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from public_bot.handlers import my_shows
from public_bot import show_utils


def _show(show_id=7):
    return SimpleNamespace(
        id=show_id, title="Шоу", team_name="Команда", poster_text="Описание",
        show_date=__import__("datetime").datetime(2099, 9, 5, 18, 0),
        location="Театр", location_url=None, city="Лимасол", max_seats=20,
        registrar_username=None, registrar=None,
    )


def test_show_text_marks_an_active_registration_and_guest_count():
    registration = SimpleNamespace(is_cancelled=False, guests=2)

    text = show_utils.show_text(_show(), seats_left=17, reg=registration)

    assert "✅ Ты записан(а): 3 чел. +2" in text
    assert "Записаться тут" not in text


@pytest.mark.asyncio
async def test_render_show_detail_reports_missing_show(monkeypatch):
    target = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(show_utils.crud, "get_show", AsyncMock(return_value=None))

    await show_utils.render_show_detail(target, 404, SimpleNamespace(id=1), AsyncMock())

    target.answer.assert_awaited_once_with("Шоу не найдено.")


@pytest.mark.asyncio
async def test_render_show_detail_uses_capacity_registration_and_keyboard(monkeypatch):
    show = _show()
    registration = SimpleNamespace(is_cancelled=False, guests=1)
    keyboard = object()
    target = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(show_utils.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(show_utils.crud, "count_active_registrations", AsyncMock(return_value=5))
    monkeypatch.setattr(show_utils.crud, "get_registration", AsyncMock(return_value=registration))
    keyboard_builder = __import__("unittest.mock").mock.Mock(return_value=keyboard)
    monkeypatch.setattr(show_utils, "show_detail_kb", keyboard_builder)

    await show_utils.render_show_detail(target, show.id, SimpleNamespace(id=2), AsyncMock())

    keyboard_builder.assert_called_once_with(show, True, 15)
    assert "2 чел. +1" in target.answer.await_args.args[0]
    assert target.answer.await_args.kwargs["reply_markup"] is keyboard


@pytest.mark.asyncio
@pytest.mark.parametrize("upcoming,expected", [
    ([], "предстоящих шоу пока нет"),
    ([_show()], "Выбери шоу"),
])
async def test_my_shows_empty_state_depends_on_available_shows(monkeypatch, upcoming, expected):
    message = SimpleNamespace(answer=AsyncMock())
    state = SimpleNamespace(clear=AsyncMock())
    monkeypatch.setattr(my_shows.crud, "get_user_registrations", AsyncMock(return_value=[]))
    monkeypatch.setattr(my_shows.crud, "list_upcoming_shows", AsyncMock(return_value=upcoming))
    monkeypatch.setattr(my_shows, "shows_list_kb", lambda *_args: "shows-keyboard")

    await my_shows.cmd_my_shows(message, state, SimpleNamespace(id=3), AsyncMock())

    state.clear.assert_awaited_once()
    assert expected in message.answer.await_args_list[0].args[0]
    if upcoming:
        assert message.answer.await_args.kwargs["reply_markup"] == "shows-keyboard"


@pytest.mark.asyncio
async def test_my_shows_lists_registrations_and_excludes_them_from_other_shows(monkeypatch):
    registered_show, other_show = _show(1), _show(2)
    registrations = [SimpleNamespace(show_id=1)]
    message = SimpleNamespace(answer=AsyncMock())
    monkeypatch.setattr(my_shows.crud, "get_user_registrations", AsyncMock(return_value=registrations))
    monkeypatch.setattr(my_shows.crud, "list_upcoming_shows", AsyncMock(return_value=[registered_show, other_show]))
    monkeypatch.setattr(my_shows, "my_shows_kb", lambda regs: ("mine", regs))
    seen = []
    monkeypatch.setattr(my_shows, "shows_list_kb", lambda shows, ids: seen.extend(shows) or ("other", ids))

    await my_shows.cmd_my_shows(message, SimpleNamespace(clear=AsyncMock()), SimpleNamespace(id=3), AsyncMock())

    assert message.answer.await_count == 2
    assert seen == [other_show]


def _callback(*, photo=False):
    message = SimpleNamespace(
        photo=[object()] if photo else [], answer=AsyncMock(), edit_text=AsyncMock(),
        edit_reply_markup=AsyncMock(), delete=AsyncMock(),
    )
    return SimpleNamespace(answer=AsyncMock(), message=message, bot=SimpleNamespace(send_message=AsyncMock()))


@pytest.mark.asyncio
async def test_cancel_registration_reports_an_already_missing_registration(monkeypatch):
    callback = _callback()
    monkeypatch.setattr(my_shows.crud, "get_show", AsyncMock(return_value=_show()))
    monkeypatch.setattr(my_shows.crud, "cancel_registration", AsyncMock(return_value=None))

    await my_shows.cancel_registration(
        callback, SimpleNamespace(show_id=7), SimpleNamespace(id=3), AsyncMock(), AsyncMock(),
    )

    callback.answer.assert_awaited_once()
    callback.message.answer.assert_awaited_once_with("Запись не найдена или уже отменена.")


@pytest.mark.asyncio
async def test_cancelling_the_last_registration_returns_to_main_menu(monkeypatch):
    callback = _callback()
    registration = SimpleNamespace(attendee_name="Анна", guests=0)
    monkeypatch.setattr(my_shows.crud, "get_show", AsyncMock(return_value=None))
    monkeypatch.setattr(my_shows.crud, "cancel_registration", AsyncMock(return_value=registration))
    monkeypatch.setattr(my_shows.crud, "get_user_registrations", AsyncMock(return_value=[]))
    monkeypatch.setattr(my_shows.crud, "list_upcoming_shows", AsyncMock(return_value=[]))
    monkeypatch.setattr("public_bot.keyboards.reply.main_menu_kb", lambda **kwargs: ("menu", kwargs))

    await my_shows.cancel_registration(
        callback, SimpleNamespace(show_id=7), SimpleNamespace(id=3), AsyncMock(), AsyncMock(),
    )

    callback.message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert "Запись на <b>шоу</b> отменена" in callback.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_cancelling_one_registration_keeps_others_and_notifies_organizers(monkeypatch):
    callback = _callback()
    show = _show(7)
    cancelled = SimpleNamespace(attendee_name="Анна", guests=1)
    remaining = [SimpleNamespace(show_id=8)]
    other = _show(9)
    notify = AsyncMock()
    admin_bot = AsyncMock()
    monkeypatch.setattr(my_shows.crud, "get_show", AsyncMock(return_value=show))
    monkeypatch.setattr(my_shows.crud, "cancel_registration", AsyncMock(return_value=cancelled))
    monkeypatch.setattr(my_shows.crud, "count_active_registrations", AsyncMock(return_value=4))
    monkeypatch.setattr(my_shows.crud, "promote_waitlist", AsyncMock(return_value=None))
    monkeypatch.setattr(my_shows.crud, "get_user_registrations", AsyncMock(return_value=remaining))
    monkeypatch.setattr(my_shows.crud, "list_upcoming_shows", AsyncMock(return_value=[_show(8), other]))
    monkeypatch.setattr(my_shows, "_notify_registration_cancellation", notify)
    monkeypatch.setattr(my_shows, "my_shows_kb", lambda regs: ("mine", regs))
    monkeypatch.setattr(my_shows, "shows_list_kb", lambda shows, ids: ("other", [show.id for show in shows], ids))

    await my_shows.cancel_registration(
        callback, SimpleNamespace(show_id=7), SimpleNamespace(id=3), AsyncMock(), admin_bot,
    )

    notify.assert_awaited_once_with(admin_bot, show, "Анна", 1, 4)
    assert "Оставшиеся записи" in callback.message.edit_text.await_args.args[0]
    assert callback.message.answer.await_args.kwargs["reply_markup"][1] == [9]
