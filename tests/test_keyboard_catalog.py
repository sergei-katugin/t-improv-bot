from datetime import timedelta
from types import SimpleNamespace

from admin_bot.keyboards import inline as admin
from admin_bot.keyboards import reply
from db.models import UserRole
from public_bot.keyboards import inline as public
from time_utils import utc_now


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def _assert_valid(markup):
    buttons = _buttons(markup)
    assert buttons
    assert all(not button.callback_data or len(button.callback_data.encode()) <= 64 for button in buttons)
    return {button.text for button in buttons}


def _show(**overrides):
    values = dict(
        id=7, title="Большое шоу", team_name="Команда", show_date=utc_now() + timedelta(days=2),
        location="Театр", location_url="https://maps.example", city="Лимасол", poster_text="Описание",
        is_active=True, checkin_enabled=True, feedback_enabled=True, registration_chat_id=-100,
        announcement_logs=[], creator=SimpleNamespace(username="owner", telegram_id=42),
        registrar=SimpleNamespace(username="registrar"), registrar_username=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_admin_show_keyboards_cover_each_state_and_section():
    future = _show()
    past = _show(id=8, show_date=utc_now() - timedelta(days=1))
    cancelled = _show(id=9, is_active=False)
    assert any("🎭" in text for text in _assert_valid(admin.shows_list_kb([future, past, cancelled], page=1, has_next=True)))
    for status in ("all", "active", "past", "cancelled"):
        _assert_valid(admin.shows_filter_kb({"status": status, "team": "Команда", "year": 2026}))
    _assert_valid(admin.show_detail_kb(future, True, True))
    _assert_valid(admin.show_detail_kb(future, False))
    for section in ("promotion", "audience", "show_settings", "danger"):
        _assert_valid(admin.show_section_kb(future, section, can_delete=True))
    _assert_valid(admin.show_section_kb(_show(is_active=False), "danger"))
    _assert_valid(admin.show_section_kb(_show(creator=SimpleNamespace(username=None, telegram_id=42)), "show_settings"))
    _assert_valid(admin.edit_notification_mode_kb(7))
    _assert_valid(admin.show_created_kb(7))
    for group in (None, "basic", "venue", "poster", "registration", "extra"):
        _assert_valid(admin.edit_show_fields_kb(future, group))


def test_admin_attendee_and_confirmation_keyboards_cover_variants():
    registrations = [
        SimpleNamespace(id=1, is_cancelled=False, checked_in_count=0, guests=2, attendee_name="Анна"),
        SimpleNamespace(id=2, is_cancelled=True, checked_in_count=0, guests=0, attendee_name="Отмена"),
        SimpleNamespace(id=3, is_cancelled=False, checked_in_count=1, guests=0, attendee_name="Борис"),
    ]
    manual = [SimpleNamespace(id=4, checked_in_count=1, name="Вручную")]
    _assert_valid(admin.checkin_kb(7, registrations, manual))
    _assert_valid(admin.checkin_mode_kb(7))
    _assert_valid(admin.checkin_counter_kb(7))
    _assert_valid(admin.party_count_kb(7, "registration", 1, 2, 6))
    _assert_valid(admin.registrations_kb(7, manual, True))
    _assert_valid(admin.registrations_kb(7, [], False))
    _assert_valid(admin.registration_chat_kb(7, True, "full"))
    _assert_valid(admin.registration_chat_kb(7, False))
    _assert_valid(admin.confirm_kb("yes", "no"))
    _assert_valid(admin.confirm_with_back_kb("yes", "no", checkin_enabled=True, feedback_enabled=True))
    _assert_valid(admin.fsm_cancel_kb())
    _assert_valid(admin.fsm_skip_cancel_kb("skip"))


def test_admin_resource_and_settings_keyboards_cover_permissions():
    admin_user = SimpleNamespace(first_name="Root", username="root", telegram_id=1, role=UserRole.admin)
    organizer = SimpleNamespace(first_name=None, username="org", telegram_id=2, role=UserRole.organizer)
    _assert_valid(admin.organizers_list_kb([admin_user, organizer]))
    _assert_valid(admin.settings_kb(False)); _assert_valid(admin.settings_kb(True))
    channels = [SimpleNamespace(id=1, username="@one", is_active=True), SimpleNamespace(id=2, username="@two", is_active=False)]
    _assert_valid(admin.ad_channels_list_kb(channels)); _assert_valid(admin.ad_channels_list_kb([]))
    _assert_valid(admin.roles_menu_kb()); _assert_valid(admin.city_kb())
    venues = [SimpleNamespace(id=1, name="A", is_active=True, default_seats=50), SimpleNamespace(id=2, name="B", is_active=False, default_seats=20)]
    _assert_valid(admin.venue_kb(venues)); _assert_valid(admin.venues_list_kb(venues))
    _assert_valid(admin.venue_detail_kb(venues[0])); _assert_valid(admin.venue_detail_kb(venues[1]))
    teams = [SimpleNamespace(id=1, name="A", is_active=True), SimpleNamespace(id=2, name="B", is_active=False)]
    _assert_valid(admin.team_kb()); _assert_valid(admin.team_select_kb(teams))
    _assert_valid(admin.team_create_fsm_skip_kb()); _assert_valid(admin.teams_list_kb(teams))
    _assert_valid(admin.team_detail_kb(teams[0], True)); _assert_valid(admin.team_detail_kb(teams[1], False))


def test_public_keyboards_cover_registration_capacity_and_reminders():
    show = _show()
    assert public.registrar_username(show) == "registrar"
    assert public.registrar_username(_show(registrar=None, registrar_username="@fallback")) == "fallback"
    _assert_valid(public.shows_list_kb([show], {show.id}))
    _assert_valid(public.show_detail_kb(show, True, 4))
    _assert_valid(public.show_detail_kb(show, False, 4))
    _assert_valid(public.show_detail_kb(_show(registration_closes_at=utc_now() - timedelta(minutes=1)), False, 4))
    _assert_valid(public.show_detail_kb(show, False, 0))
    _assert_valid(public.manage_registration_kb(7)); _assert_valid(public.guests_kb(7, 99))
    _assert_valid(public.confirm_registration_kb(7))
    _assert_valid(public.reminder_prefs_kb(7, True, False, True))
    _assert_valid(public.registration_success_kb(show, True, False, True))
    _assert_valid(public.attendance_kb(7)); _assert_valid(public.reminder_cancel_kb(7))
    _assert_valid(public.calendar_kb(show)); _assert_valid(public.calendar_kb(_show(location_url=None)))
    _assert_valid(public.feedback_kb(7))
    registration = SimpleNamespace(show=show, show_id=show.id, guests=2)
    _assert_valid(public.my_shows_kb([registration]))


def test_reply_keyboards_expose_each_reduced_bot_context(monkeypatch):
    monkeypatch.setattr(reply.settings, "WEBHOOK_BASE_URL", "https://example.com")
    assert reply.miniapp_launch_kb() is not None
    for factory in (
        reply.main_menu_kb, reply.shows_context_kb, reply.show_context_kb,
        reply.promotion_context_kb, reply.registrations_context_kb,
        reply.flow_context_kb, reply.registration_channel_picker_kb,
    ):
        assert factory().keyboard
    assert reply.settings_context_kb(False).keyboard
    assert reply.settings_context_kb(True).keyboard
