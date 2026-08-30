from datetime import datetime
from types import SimpleNamespace

from admin_bot.handlers.shows import _preview_from_data, _tracked_show_link
from admin_bot.keyboards.inline import confirm_with_back_kb, edit_show_fields_kb
from admin_bot.keyboards.reply import flow_context_kb, show_context_kb, shows_context_kb
from db.models import Show
from public_bot.handlers.registration import _ics_escape, _registration_privacy_note
from public_bot.keyboards.inline import calendar_kb, feedback_kb, registration_success_kb
from public_bot.show_utils import show_text


def test_tracked_show_link_contains_source():
    link = _tracked_show_link(42, "instagram")
    assert link.endswith("?start=show_42_instagram")


def test_registration_discloses_name_visibility_before_confirmation():
    assert "сокращённом виде" in _registration_privacy_note({"registration_chat_name_mode": "short"})
    assert "полностью" in _registration_privacy_note({"registration_chat_name_mode": "full"})
    assert _registration_privacy_note({}) == ""


def test_feedback_is_disabled_by_default():
    assert Show().feedback_enabled is None
    assert Show.__table__.c.feedback_enabled.default.arg is False


def test_create_confirmation_exposes_optional_features():
    keyboard = confirm_with_back_kb(
        "confirm",
        "cancel",
        checkin_enabled=True,
        feedback_enabled=False,
    )
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.text == "🎟 Режим входа: вкл" for button in buttons)
    assert any(button.text == "⭐ Отзывы: выкл" for button in buttons)


def test_create_preview_hides_optional_feature_statuses():
    preview = _preview_from_data({
        "title": "Test Show",
        "team_name": "Test <Team>",
        "show_date_str": "29 августа, 19:00",
        "location": "Theatre",
        "city": "Limassol",
        "registrar_username": "alice",
        "checkin_enabled": False,
        "feedback_enabled": False,
    })

    assert "Check-in" not in preview
    assert "Отзывы после шоу" not in preview
    assert "👥 Команда: Test &lt;Team&gt;" in preview
    assert "👥 Записаться тут:" in preview
    assert "<b>через бота</b>" in preview
    assert "@ImprovCypEventBot</a> или у <a href=\"https://t.me/alice\">@alice</a>" in preview


def test_edit_keyboard_exposes_current_optional_feature_values():
    show = Show(id=42, checkin_enabled=False, feedback_enabled=True)
    main_buttons = [button for row in edit_show_fields_kb(show).inline_keyboard for button in row]
    assert any(button.text == "🎭 Основное" for button in main_buttons)
    assert any(button.text == "📝 Афиша" for button in main_buttons)
    buttons = [button for row in edit_show_fields_kb(show, "extra").inline_keyboard for button in row]
    assert any(button.text == "🎟 Режим входа: выкл" for button in buttons)
    assert any(button.text == "⭐ Отзывы: вкл" for button in buttons)


def test_registration_success_is_one_keyboard_with_calendar_and_reminders():
    show = SimpleNamespace(
        id=42, title="Show", show_date=datetime(2026, 8, 29, 17, 0),
        location="Venue", city="Limassol", poster_text=None,
    )
    buttons = [button for row in registration_success_kb(show, False, False, True).inline_keyboard for button in row]
    assert any(button.text == "📅 Google Calendar" for button in buttons)
    assert any(button.text == "✅ Напомнить за день" for button in buttons)
    assert any(button.text == "⚙️ Управлять записью" for button in buttons)


def test_registration_success_includes_registrar_contact_when_available():
    show = SimpleNamespace(
        id=42, title="Show", show_date=datetime(2026, 8, 29, 17, 0),
        location="Venue", city="Limassol", poster_text=None,
        registrar=SimpleNamespace(username="@alice"), registrar_username=None,
    )
    buttons = [button for row in registration_success_kb(show, False, False, True).inline_keyboard for button in row]
    contact = next(button for button in buttons if button.text == "💬 Помощь с записью")
    assert contact.url == "https://t.me/alice"


def test_admin_context_keyboards_never_exceed_four_actions():
    for keyboard in (shows_context_kb(), show_context_kb(), flow_context_kb()):
        buttons = [button for row in keyboard.keyboard for button in row]
        assert len(buttons) <= 4
    show_labels = {button.text for row in show_context_kb().keyboard for button in row}
    assert show_labels == {"👥 Записи", "✏️ Редактировать", "📣 Продвижение", "◀️ К списку шоу"}


def test_calendar_keyboard_has_google_ics_and_route():
    show = SimpleNamespace(
        id=42,
        title="Test Show",
        show_date=datetime(2026, 8, 29, 17, 0),
        location="Theatre",
        city="Limassol",
        poster_text="Description",
        location_url="https://maps.google.com/example",
    )
    buttons = [button for row in calendar_kb(show).inline_keyboard for button in row]
    assert any(button.url and "calendar.google.com" in button.url for button in buttons)
    assert any(button.callback_data and button.callback_data.startswith("calendar:") for button in buttons)
    assert any(button.url == show.location_url for button in buttons)


def test_public_show_text_links_location_without_extra_separator_spaces():
    show = SimpleNamespace(
        title="Test Show",
        team_name="Test Team",
        show_date=datetime(2026, 8, 29, 17, 0),
        location="Ena Theatre",
        location_url="https://maps.example/theatre",
        city="Limassol",
        max_seats=80,
        registrar=None,
        registrar_username=None,
        poster_text=None,
    )

    text = show_text(show, seats_left=80)

    assert (
        '📍 <a href="https://maps.example/theatre">Ena Theatre</a>, Limassol'
        in text
    )
    assert "Записаться тут" not in text
    assert "https://t.me/" not in text


def test_feedback_keyboard_has_five_ratings():
    buttons = [button for row in feedback_kb(42).inline_keyboard for button in row]
    assert len(buttons) == 5
    assert {button.text for button in buttons} == {"1 ⭐", "2 ⭐", "3 ⭐", "4 ⭐", "5 ⭐"}


def test_ics_escape_protects_special_characters():
    assert _ics_escape("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"
