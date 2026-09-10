from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

import miniapp_api
from admin_bot.handlers import registrations, shows
from scheduler import jobs
from time_utils import utc_now


def _show(**overrides):
    values = dict(
        id=7,
        title="Супер <шоу>",
        team_name="Команда",
        show_date=utc_now() + timedelta(days=2),
        location="Театр",
        location_url="https://maps.example/venue?a=1&b=2",
        city="Лимасол",
        poster_text="Описание",
        max_seats=80,
        registrar=None,
        registrar_username=None,
        poster_file_id=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_admin_show_formatting_and_validation_helpers():
    assert "3/8" in shows._progress(3)
    assert shows._registrar_name(SimpleNamespace(first_name="Анна", username="a", telegram_id=1)) == "Анна"
    assert shows._registrar_name(SimpleNamespace(first_name=None, username="a", telegram_id=1)) == "@a"
    assert shows._registrar_name(SimpleNamespace(first_name=None, username=None, telegram_id=1)) == "id1"
    assert shows._registrar_name(None, "owner") == "@owner"
    assert shows._registrar_link(None, "<owner>") == "&lt;owner&gt;"
    assert "https://t.me/owner" in shows._registrar_link("@owner")
    assert "Проверьте данные" in shows._show_summary({
        "title": "T", "team_name": "G", "show_date_str": "date", "city": "C",
        "location": "V", "location_url": "https://maps.example", "max_seats": 10,
        "poster_text": None, "poster_file_id": "photo", "registrar_username": "owner",
    })
    assert shows._validate_poster_text("x" * (shows.MAX_POSTER_TEXT_LENGTH + 1))
    assert "дату" in shows._validate_poster_text("Шоу 01.01.2099")
    assert "время" in shows._validate_poster_text("Шоу в 19:00")
    assert "Google Maps" in shows._validate_poster_text("https://maps.google.com/test")
    assert shows._validate_poster_text("Обычное описание") is None
    assert shows._is_google_maps_url("https://maps.app.goo.gl/test")
    assert not shows._is_google_maps_url("https://example.com")


@pytest.mark.parametrize("value,expected", [(None, ""), ("=1+1", "'=1+1"), ("name", "name")])
def test_admin_csv_cells_are_safe(value, expected):
    assert registrations._csv_cell(value) == expected


def test_scheduler_announcement_variants():
    show = _show(registrar_username="owner")
    text = jobs.build_announcement_text(show, "1d", seats_left=12, attendee_line="Уже идут: 5")
    assert "Завтра" in text
    assert "Свободных мест" not in text
    assert "Уже идут: 5" in text
    assert "https://t.me/owner" in text
    assert "&lt;шоу&gt;" in text
    lines = text.splitlines()
    assert lines[0] == "🎭 <b>Команда Команда представляет шоу Супер &lt;шоу&gt;</b>"
    date_index = next(index for index, line in enumerate(lines) if line.startswith("📅"))
    location_index = next(index for index, line in enumerate(lines) if line.startswith("📍"))
    registration_index = next(index for index, line in enumerate(lines) if "Записаться тут" in line)
    poster_index = lines.index("Описание")
    assert date_index < location_index < registration_index < poster_index
    assert "👥 Команда:" not in text
    assert jobs._register_button(None) is None
    assert jobs._register_button(SimpleNamespace(id=None)) is None
    assert jobs._register_button(show).inline_keyboard[0][0].url.endswith("show_7")

    embedded = _show(poster_text="01.01.2099 https://maps.google.com/place", registrar_username=None)
    embedded_text = jobs.build_announcement_text(embedded, include_registration=False)
    assert "через бота" not in embedded_text
    assert "📅" not in embedded_text
    assert "<a href=" not in embedded_text
    reminder, keyboard = jobs.build_personal_reminder(show, "Скоро!")
    assert reminder.startswith("Скоро!") and keyboard is not None


@pytest.mark.parametrize("payload", [
    {},
    {"title": ""},
    {"title": "x" * 257},
    {"maxGuests": 7},
    {"maxGuests": True},
    {"checkinEnabled": "yes"},
])
def test_miniapp_show_patch_rejects_invalid_values(payload):
    if not payload:
        assert miniapp_api._show_fields(payload, require_all=False) == {}
    else:
        with pytest.raises(web.HTTPBadRequest):
            miniapp_api._show_fields(payload, require_all=False)


def test_miniapp_show_patch_accepts_nullable_and_bounded_values():
    future = utc_now() + timedelta(days=4)
    payload = {
        "maxGuests": 0,
        "registrarUsername": "",
        "locationUrl": "",
        "posterText": " ",
        "feedbackEnabled": False,
    }
    result = miniapp_api._show_fields(payload, require_all=False)
    assert result == {
        "location_url": None,
        "poster_text": None,
        "max_guests": 0,
        "registrar_username": None,
        "feedback_enabled": False,
    }
    dates = miniapp_api._show_fields({
        "showDateLocal": future.isoformat(),
        "registrationClosesAt": (future + timedelta(hours=1)).isoformat(),
    }, require_all=False)
    assert dates["registration_closes_at"] == dates["show_date"] - timedelta(minutes=5)


@pytest.mark.asyncio
async def test_miniapp_json_body_limits_and_shape():
    request = SimpleNamespace(content_length=40_000, json=AsyncMock())
    with pytest.raises(web.HTTPRequestEntityTooLarge):
        await miniapp_api._json_body(request)
    request = SimpleNamespace(content_length=None, json=AsyncMock(side_effect=ValueError))
    with pytest.raises(web.HTTPBadRequest) as exc_info:
        await miniapp_api._json_body(request)
    assert "invalid_json" in exc_info.value.text
    request = SimpleNamespace(content_length=None, json=AsyncMock(return_value=[]))
    with pytest.raises(web.HTTPBadRequest) as exc_info:
        await miniapp_api._json_body(request)
    assert "invalid_payload" in exc_info.value.text
    request.json = AsyncMock(return_value={"ok": True})
    assert await miniapp_api._json_body(request) == {"ok": True}


@pytest.mark.asyncio
async def test_registration_chat_verification_variants():
    bot = AsyncMock()
    with pytest.raises(web.HTTPBadRequest):
        await miniapp_api._verified_registration_chat(bot, "not-an-id")

    chat = SimpleNamespace(id=-100, title="Наш чат", username=None, type="supergroup")
    bot.get_chat.return_value = chat
    bot.get_me.return_value = SimpleNamespace(id=5)
    bot.get_chat_member.return_value = SimpleNamespace(status="member")
    actual, title = await miniapp_api._verified_registration_chat(bot, "−100")
    assert actual is chat and title == "Наш чат"

    chat.type = "channel"
    with pytest.raises(web.HTTPConflict) as exc_info:
        await miniapp_api._verified_registration_chat(bot, "-100")
    assert "bot_cannot_post" in exc_info.value.text
    bot.get_chat_member.return_value = SimpleNamespace(status="administrator", can_post_messages=False)
    with pytest.raises(web.HTTPConflict) as exc_info:
        await miniapp_api._verified_registration_chat(bot, "-100")
    assert "bot_cannot_post" in exc_info.value.text
