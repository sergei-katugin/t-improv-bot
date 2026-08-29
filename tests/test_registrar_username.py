from types import SimpleNamespace

from admin_bot.telegram_usernames import (
    normalize_telegram_username,
    normalize_telegram_username_list,
    render_telegram_username_list,
    serialize_telegram_usernames,
)
from scheduler.jobs import _registrar_line


def test_normalize_telegram_username_accepts_variants():
    assert normalize_telegram_username("@alice") == "alice"
    assert normalize_telegram_username("alice") == "alice"
    assert normalize_telegram_username("https://t.me/alice") == "alice"


def test_normalize_telegram_username_rejects_invalid_value():
    assert normalize_telegram_username("   ") is None
    assert normalize_telegram_username("@") is None
    assert normalize_telegram_username("ab cd") is None


def test_normalize_telegram_username_normalizes_case_and_link_suffix():
    assert normalize_telegram_username("@Alice_123") == "alice_123"
    assert normalize_telegram_username("https://t.me/Alice_123/") == "alice_123"


def test_registrar_line_links_username():
    show = SimpleNamespace(registrar=None, registrar_username="alice")
    assert _registrar_line(show) == (
        '👥 Записаться тут: '
        '<b>через бота</b> '
        '<a href="https://t.me/ImprovCypEventBot">@ImprovCypEventBot</a> или у '
        '<a href="https://t.me/alice">@alice</a>'
    )


def test_registrar_line_links_public_bot_without_registrar():
    show = SimpleNamespace(registrar=None, registrar_username=None)
    assert _registrar_line(show) == (
        '👥 Записаться тут: '
        '<b>через бота</b> '
        '<a href="https://t.me/ImprovCypEventBot">@ImprovCypEventBot</a>'
    )


def test_team_members_are_normalized_and_deduplicated():
    usernames = normalize_telegram_username_list("@Alice_1, bob_22; @alice_1")
    assert usernames == ["alice_1", "bob_22"]
    assert serialize_telegram_usernames(usernames) == "@alice_1, @bob_22"


def test_team_members_render_as_clickable_links():
    rendered = render_telegram_username_list("@alice_1, @bob_22")
    assert '<a href="https://t.me/alice_1">@alice_1</a>' in rendered
    assert '<a href="https://t.me/bob_22">@bob_22</a>' in rendered
