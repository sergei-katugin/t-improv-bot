from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import miniapp_api
from admin_bot.keyboards import reply as reply_keyboards
from db.base import Base
from db.models import AuditLog, AnnouncementLog, ManualAttendee, Registration, Show, ShowFeedback, User, UserRole
from miniapp_api import (
    MiniAppAuthError, _audit_details, _csv_value, _require_admin, _set_miniapp_security_headers,
    _show_fields, miniapp_request_logging_middleware, validate_telegram_init_data,
)
from time_utils import utc_now


BOT_TOKEN = "123456:MINIAPP_TEST_TOKEN"
NOW = 1_800_000_000


def _signed_init_data(*, auth_date: int = NOW, user_id: int = 42, extra=None) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": user_id, "first_name": "Sergey", "username": "sergey"},
            separators=(",", ":"),
        ),
    }
    fields.update(extra or {})
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def test_miniapp_accepts_valid_telegram_signature():
    user = validate_telegram_init_data(_signed_init_data(), BOT_TOKEN, now=NOW)

    assert user.telegram_id == 42
    assert user.username == "sergey"
    assert user.first_name == "Sergey"


def test_miniapp_rejects_tampered_user():
    init_data = _signed_init_data().replace("%3A42", "%3A43")

    with pytest.raises(MiniAppAuthError, match="signature"):
        validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)


@pytest.mark.parametrize("auth_date", [NOW - 3601, NOW + 31])
def test_miniapp_rejects_expired_or_future_auth_data(auth_date):
    with pytest.raises(MiniAppAuthError, match="expired"):
        validate_telegram_init_data(_signed_init_data(auth_date=auth_date), BOT_TOKEN, now=NOW)


def test_miniapp_rejects_duplicate_fields():
    init_data = _signed_init_data() + "&auth_date=1800000000"

    with pytest.raises(MiniAppAuthError, match="duplicate"):
        validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)


def test_miniapp_rejects_malformed_query_string():
    with pytest.raises(MiniAppAuthError, match="malformed"):
        validate_telegram_init_data("broken", BOT_TOKEN, now=NOW)


def test_miniapp_rejects_non_object_user():
    with pytest.raises(MiniAppAuthError, match="Telegram user"):
        validate_telegram_init_data(
            _signed_init_data(extra={"user": "[]"}), BOT_TOKEN, now=NOW,
        )


def _valid_show_payload():
    return {
        "title": "Новое шоу", "teamName": "T·IMPRO", "showDateLocal": "2099-09-05T20:00",
        "location": "Театр", "locationUrl": "https://maps.example/venue", "city": "Лимасол",
        "posterText": "Текст", "maxSeats": 50, "registrarUsername": "@sergey",
        "checkinEnabled": True, "feedbackEnabled": True,
    }


def test_miniapp_show_payload_is_normalized_and_whitelisted():
    fields = _show_fields(_valid_show_payload(), require_all=True)

    assert fields["team_name"] == "T·IMPRO"
    assert fields["registrar_username"] == "sergey"
    assert fields["max_seats"] == 50

    with pytest.raises(web.HTTPBadRequest):
        _show_fields({**_valid_show_payload(), "creator_id": 999}, require_all=True)


@pytest.mark.parametrize("field,value", [
    ("locationUrl", "javascript:alert(1)"),
    ("registrarUsername", "bad username"),
    ("maxSeats", 0),
    ("showDateLocal", "2020-01-01T10:00"),
])
def test_miniapp_rejects_invalid_show_fields(field, value):
    with pytest.raises(web.HTTPBadRequest):
        _show_fields({**_valid_show_payload(), field: value}, require_all=True)


@pytest.mark.asyncio
async def test_miniapp_preview_is_sent_only_to_current_telegram_user():
    bot = type("Bot", (), {"send_message": AsyncMock()})()

    class Request(dict):
        content_length = None

        def __init__(self):
            super().__init__(miniapp_telegram_id=42)
            self.app = {miniapp_api.ADMIN_BOT_KEY: bot}

        async def json(self):
            return _valid_show_payload()

    response = await miniapp_api.miniapp_send_show_preview(Request())

    assert response.status == 200
    assert bot.send_message.await_args.args[0] == 42
    assert "Предпросмотр" in bot.send_message.await_args.args[1]


class _Request(dict):
    def __init__(self, *, show_id: int, user_id: int, is_admin: bool = False, body=None):
        super().__init__(miniapp_user_id=user_id, miniapp_is_admin=is_admin)
        self.match_info = {"show_id": str(show_id)}
        self.query = {}
        self.content_length = None
        self._body = body

    async def json(self):
        return self._body


def test_miniapp_admin_resources_require_admin_role():
    with pytest.raises(web.HTTPForbidden):
        _require_admin({"miniapp_is_admin": False})
    _require_admin({"miniapp_is_admin": True})


@pytest.mark.parametrize("value,expected", [
    ("=HYPERLINK(\"bad\")", "'=HYPERLINK(\"bad\")"),
    ("@SUM(A1:A2)", "'@SUM(A1:A2)"),
    ("обычный текст", "обычный текст"),
])
def test_csv_export_neutralizes_spreadsheet_formulas(value, expected):
    assert _csv_value(value) == expected


def test_malformed_audit_details_do_not_break_the_whole_log():
    assert _audit_details('{"broken"') == {"unavailable": True}


@pytest.mark.parametrize("path,expected_header", [
    ("/api/miniapp/me", ("Cache-Control", "private, no-store")),
    ("/app", ("Content-Security-Policy", "default-src 'self'")),
    ("/app", ("Cache-Control", "no-store")),
    ("/app/assets/index-deploy.js", ("Cache-Control", "immutable")),
])
def test_miniapp_security_headers(path, expected_header):
    request = type("Request", (), {"path": path})()
    response = web.Response()

    _set_miniapp_security_headers(request, response)

    name, expected = expected_header
    assert expected in response.headers[name]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_miniapp_button_url_is_versioned_per_render_deploy(monkeypatch):
    monkeypatch.setattr(reply_keyboards.settings, "WEBHOOK_BASE_URL", "https://example.com")
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abcdef1234567890")

    assert reply_keyboards._miniapp_url() == "https://example.com/app?v=abcdef123456"


@pytest.mark.asyncio
async def test_miniapp_request_logging_adds_request_id():
    request = type(
        "Request", (dict,), {"path": "/api/miniapp/me", "method": "GET"},
    )()

    async def handler(_request):
        return web.json_response({"ok": True})

    response = await miniapp_request_logging_middleware(request, handler)

    assert len(response.headers["X-Request-ID"]) == 12
    assert request["miniapp_request_id"] == response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_miniapp_request_logging_returns_traceable_internal_error():
    request = type(
        "Request", (dict,), {"path": "/api/miniapp/me", "method": "GET"},
    )()

    async def handler(_request):
        raise RuntimeError("unexpected failure")

    response = await miniapp_request_logging_middleware(request, handler)
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload == {
        "error": "internal_error",
        "requestId": response.headers["X-Request-ID"],
    }


@pytest.mark.asyncio
async def test_miniapp_show_detail_hides_another_organizers_show(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=100, role=UserRole.organizer)
            other = User(telegram_id=200, role=UserRole.organizer)
            session.add_all([owner, other])
            await session.flush()
            show = Show(
                title="Private", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id, other_id = show.id, other.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_show_detail(
                _Request(show_id=show_id, user_id=other_id),
            )
        response = await miniapp_api.miniapp_show_detail(
            _Request(show_id=show_id, user_id=other_id, is_admin=True),
        )
        assert response.status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_miniapp_manual_attendees_require_show_ownership(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=300, role=UserRole.organizer)
            other = User(telegram_id=400, role=UserRole.organizer)
            session.add_all([owner, other])
            await session.flush()
            show = Show(
                title="Owned", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=2, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id, owner_id, other_id = show.id, owner.id, other.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        body = {"rows": [{"name": "Manual", "contact": "@manual"}]}

        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_add_manual_attendees(
                _Request(show_id=show_id, user_id=other_id, body=body),
            )
        response = await miniapp_api.miniapp_add_manual_attendees(
            _Request(show_id=show_id, user_id=owner_id, body=body),
        )
        assert response.status == 201
        async with sessions() as session:
            attendees = await miniapp_api.crud.get_manual_attendees(session, show_id)
            assert [(item.name, item.contact) for item in attendees] == [("Manual", "@manual")]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_announcement_claim_prevents_duplicate_publish_and_can_be_released():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=500, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Publish", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id

        async with sessions() as session:
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is False
            await miniapp_api.crud.release_announcement_claim(session, show_id, "manual")
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True

        async with sessions() as session:
            logs = list((await session.scalars(
                miniapp_api.select(AnnouncementLog).where(AnnouncementLog.show_id == show_id)
            )).all())
            assert [log.announcement_type for log in logs] == ["manual"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repeat_claim_is_idempotent_per_request_key():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=600, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Repeat", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id
        async with sessions() as session:
            first_type = await miniapp_api.crud.claim_repeat_announcement(
                session, show_id, "0123456789abcdef",
            )
            assert first_type is not None
            assert await miniapp_api.crud.claim_repeat_announcement(
                session, show_id, "0123456789abcdef",
            ) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clone_show_preserves_configuration_but_uses_new_date(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=700, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            source = Show(
                title="Clone me", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", location_url="https://maps.example/venue", city="City",
                poster_text="Poster", poster_file_id="telegram-file", max_seats=33,
                creator_id=owner.id, registrar_username="sergey", checkin_enabled=True,
                feedback_enabled=True,
            )
            session.add(source)
            await session.commit()
            show_id, owner_id = source.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        response = await miniapp_api.miniapp_clone_show(_Request(
            show_id=show_id, user_id=owner_id, body={"showDateLocal": "2099-10-10T20:30"},
        ))
        payload = json.loads(response.text)
        async with sessions() as session:
            clone = await session.get(Show, payload["id"])
            assert clone is not None
            assert (clone.title, clone.poster_file_id, clone.max_seats) == (
                "Clone me", "telegram-file", 33,
            )
            assert clone.checkin_enabled is True
            assert clone.feedback_enabled is True
            assert clone.id != show_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deactivate_show_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=800, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Cancel", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id
        async with sessions() as session:
            assert await miniapp_api.crud.deactivate_show(session, show_id) is True
            assert await miniapp_api.crud.deactivate_show(session, show_id) is False
            cancelled = await session.get(Show, show_id)
            assert cancelled is not None and cancelled.is_active is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_analytics_aggregates_people_sources_and_feedback(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=900, role=UserRole.organizer)
            viewer = User(telegram_id=901, username="viewer", first_name="Viewer")
            cancelled_viewer = User(telegram_id=902, first_name="Cancelled")
            session.add_all([owner, viewer, cancelled_viewer])
            await session.flush()
            show = Show(
                title="Analytics", team_name="Team", show_date=utc_now() - timedelta(hours=3),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
                checkin_enabled=True, feedback_enabled=True,
            )
            session.add(show)
            await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=1, source="instagram", confirmed=True, checked_in_count=2),
                Registration(show_id=show.id, user_id=cancelled_viewer.id, attendee_name="Cancelled", is_cancelled=True),
                ManualAttendee(show_id=show.id, name="Manual", source="manual", checked_in_count=1),
                ShowFeedback(show_id=show.id, user_id=viewer.id, rating=5, comment="Great"),
            ])
            await session.commit()
            show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        response = await miniapp_api.miniapp_show_analytics(
            _Request(show_id=show_id, user_id=owner_id),
        )
        payload = json.loads(response.text)
        assert payload["registered"] == 3
        assert payload["arrived"] == 3
        assert payload["confirmed"] == 2
        assert payload["cancelledRegistrations"] == 1
        assert payload["averageRating"] == 5.0
        assert payload["sources"] == [
            {"source": "instagram", "count": 2},
            {"source": "manual", "count": 1},
        ]
        assert payload["comments"][0]["comment"] == "Great"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_access_role_update_protects_self_and_admin_but_revokes_organizer(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=1000, username="admin", role=UserRole.admin)
            organizer = User(telegram_id=1001, username="organizer", role=UserRole.organizer)
            session.add_all([admin, organizer])
            await session.commit()
            admin_id, organizer_id = admin.id, organizer.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        self_request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"role": "user"})
        self_request.match_info = {"user_id": str(admin_id)}
        with pytest.raises(web.HTTPConflict):
            await miniapp_api.miniapp_update_access_user(self_request)

        revoke_request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"role": "user"})
        revoke_request.match_info = {"user_id": str(organizer_id)}
        response = await miniapp_api.miniapp_update_access_user(revoke_request)
        assert response.status == 200
        async with sessions() as session:
            organizer = await session.get(User, organizer_id)
            assert organizer is not None and organizer.role == UserRole.user
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_access_invite_is_organizer_only_and_expires(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=0, user_id=1, is_admin=True, body={"role": "organizer"})
        response = await miniapp_api.miniapp_create_access_invite(request)
        payload = json.loads(response.text)
        assert response.status == 201
        assert payload["role"] == "organizer"
        assert payload["expiresAt"] is not None
        assert "?start=inv_" in payload["url"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_log_records_actor_and_is_admin_only(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=1100, username="audit_admin", role=UserRole.admin)
            session.add(admin)
            await session.commit()
            admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=42, user_id=admin_id, is_admin=True)
        await miniapp_api._record_audit(
            request, "show.cancelled", "show", 42, {"safe": True},
        )
        response = await miniapp_api.miniapp_audit_log(request)
        payload = json.loads(response.text)
        assert payload["items"][0]["action"] == "show.cancelled"
        assert payload["items"][0]["actor"]["username"] == "audit_admin"
        assert payload["items"][0]["details"] == {"safe": True}
        async with sessions() as session:
            assert await session.scalar(miniapp_api.select(AuditLog)) is not None

        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_audit_log(
                _Request(show_id=42, user_id=admin_id, is_admin=False),
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_list_filters_by_team_year_and_paginates(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1200, role=UserRole.organizer)
            session.add(owner); await session.flush()
            session.add_all([
                Show(title="First", team_name="Alpha", show_date=utc_now() + timedelta(days=10), location="V", city="C", max_seats=10, creator_id=owner.id),
                Show(title="Second", team_name="Alpha", show_date=utc_now() + timedelta(days=9), location="V", city="C", max_seats=10, creator_id=owner.id),
                Show(title="Other", team_name="Beta", show_date=utc_now() + timedelta(days=8), location="V", city="C", max_seats=10, creator_id=owner.id),
            ])
            await session.commit(); owner_id = owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(miniapp_api, "MAX_SHOWS_PER_PAGE", 1)
        request = _Request(show_id=0, user_id=owner_id)
        request.query = {"status": "upcoming", "team": "Alpha", "year": str((utc_now() + timedelta(days=10)).year), "offset": "0"}
        first = json.loads((await miniapp_api.miniapp_shows(request)).text)
        assert [item["teamName"] for item in first["items"]] == ["Alpha"]
        assert first["hasMore"] is True and first["nextOffset"] == 1
        request.query["offset"] = "1"
        second = json.loads((await miniapp_api.miniapp_shows(request)).text)
        assert len(second["items"]) == 1 and second["hasMore"] is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attendee_search_matches_name_username_and_manual_contact(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1300, role=UserRole.organizer)
            viewer = User(telegram_id=1301, username="find_me")
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Search", team_name="Team", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=20, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=viewer.id, attendee_name="Telegram Viewer"),
                ManualAttendee(show_id=show.id, name="Manual Viewer", contact="@manual_find"),
            ])
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id); request.query = {"search": "find_me"}
        by_username = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert [item["username"] for item in by_username["registrations"]] == ["find_me"]
        request.query = {"search": "manual_find"}
        by_contact = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert [item["name"] for item in by_contact["manual"]] == ["Manual Viewer"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dictionary_delete_enforces_owner_and_admin_roles(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1400, role=UserRole.organizer)
            other = User(telegram_id=1401, role=UserRole.organizer)
            session.add_all([owner, other]); await session.flush()
            team = await miniapp_api.crud.create_team(session, "Owned", None, owner.id)
            team_id, owner_id, other_id = team.id, owner.id, other.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        denied = _Request(show_id=0, user_id=other_id); denied.match_info = {"team_id": str(team_id)}
        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_delete_team(denied)
        allowed = _Request(show_id=0, user_id=owner_id); allowed.match_info = {"team_id": str(team_id)}
        assert (await miniapp_api.miniapp_delete_team(allowed)).status == 200

        venue_request = _Request(show_id=0, user_id=owner_id, body={"name": "V", "city": "C", "defaultSeats": 10})
        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_create_venue(venue_request)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancelled_show_can_be_restored_then_deleted_by_owner(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1500, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Restore", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id, is_active=False)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id)
        restored = json.loads((await miniapp_api.miniapp_restore_show(request)).text)
        assert restored["isActive"] is True
        assert (await miniapp_api.miniapp_delete_show(request)).status == 200
        async with sessions() as session:
            assert await session.get(Show, show_id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_chat_is_verified_before_it_is_saved(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1600, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Chat", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(id=-100123, title="Registrations", username=None, type="channel")),
            get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_post_messages=True)),
            send_message=AsyncMock(),
        )
        request = _Request(show_id=show_id, user_id=owner_id, body={"target": "@registrations", "nameMode": "full"})
        request.app = {miniapp_api.ADMIN_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_registration_chat(request)).text)
        assert payload == {"id": -100123, "title": "Registrations", "nameMode": "full"}
        bot.send_message.assert_awaited_once()
        async with sessions() as session:
            saved = await session.get(Show, show_id)
            assert (saved.registration_chat_id, saved.registration_chat_name_mode) == (-100123, "full")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reminders_are_sent_only_to_active_registered_users(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1700, role=UserRole.organizer)
            active = User(telegram_id=1701, username="active")
            cancelled = User(telegram_id=1702, username="cancelled")
            session.add_all([owner, active, cancelled]); await session.flush()
            show = Show(title="Reminder", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=active.id, attendee_name="Active"),
                Registration(show_id=show.id, user_id=cancelled.id, attendee_name="Cancelled", is_cancelled=True),
            ])
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(send_message=AsyncMock())
        request = _Request(show_id=show_id, user_id=owner_id); request.app = {miniapp_api.PUBLIC_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_remind_viewers(request)).text)
        assert payload == {"sent": 1, "failed": 0}
        assert bot.send_message.await_args.args[0] == 1701
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_update_notifies_viewers_only_when_requested(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1800, role=UserRole.organizer)
            viewer = User(telegram_id=1801, username="viewer")
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Before", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add(Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer"))
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(send_message=AsyncMock())
        request = _Request(show_id=show_id, user_id=owner_id, body={"title": "After <b>", "notify": True})
        request.app = {miniapp_api.PUBLIC_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_update_show(request)).text)
        assert payload == {"id": show_id, "notified": 1, "failed": 0}
        assert bot.send_message.await_args.args[0] == 1801
        assert "After &lt;b&gt;" in bot.send_message.await_args.args[1]

        bot.send_message.reset_mock()
        request._body = {"title": "Silent", "notify": False}
        payload = json.loads((await miniapp_api.miniapp_update_show(request)).text)
        assert payload["notified"] == 0
        bot.send_message.assert_not_awaited()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_tasks_and_manual_notification_confirmation(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1900, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Tasks", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add(ManualAttendee(show_id=show.id, name="Manual"))
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id)
        tasks = json.loads((await miniapp_api.miniapp_show_tasks(request)).text)["items"]
        assert {item["key"] for item in tasks} == {"announcement", "registration_chat", "manual_notifications"}

        confirmed = json.loads((await miniapp_api.miniapp_confirm_manual_notifications(request)).text)
        assert confirmed == {"confirmed": 1}
        tasks = json.loads((await miniapp_api.miniapp_show_tasks(request)).text)["items"]
        assert "manual_notifications" not in {item["key"] for item in tasks}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_middleware_rejects_invalid_signature(monkeypatch):
    class Request(dict):
        path = "/api/miniapp/me"
        headers = {"Authorization": "tma invalid"}

    def reject(*_args, **_kwargs):
        raise MiniAppAuthError("bad signature")

    monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", reject)
    handler = AsyncMock()
    with pytest.raises(web.HTTPUnauthorized) as error:
        await miniapp_api.miniapp_auth_middleware(Request(), handler)
    assert json.loads(error.value.text) == {"error": "telegram_auth_failed"}
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_middleware_sets_organizer_context_and_rejects_regular_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            organizer = User(telegram_id=2000, role=UserRole.organizer)
            regular = User(telegram_id=2001, role=UserRole.user)
            session.add_all([organizer, regular]); await session.commit()
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        class Request(dict):
            path = "/api/miniapp/me"
            headers = {"Authorization": "tma signed"}

        handler = AsyncMock(return_value=web.json_response({"ok": True}))
        monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", lambda *_args, **_kwargs: SimpleNamespace(telegram_id=2000))
        request = Request()
        response = await miniapp_api.miniapp_auth_middleware(request, handler)
        assert response.status == 200
        assert request["miniapp_telegram_id"] == 2000
        assert request["miniapp_is_admin"] is False

        monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", lambda *_args, **_kwargs: SimpleNamespace(telegram_id=2001))
        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_auth_middleware(Request(), handler)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_publish_releases_claim_for_retry(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2100, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(
                title="Publish failure", team_name="T", show_date=utc_now() + timedelta(days=1),
                location="V", city="C", max_seats=10, creator_id=owner.id,
                poster_text="Ready", poster_file_id="file-id",
            )
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr("scheduler.jobs.send_to_channel", AsyncMock(side_effect=RuntimeError("telegram unavailable")))
        request = _Request(show_id=show_id, user_id=owner_id, body={})
        request.app = {miniapp_api.PUBLIC_BOT_KEY: object(), miniapp_api.ADMIN_BOT_KEY: object()}
        with pytest.raises(RuntimeError, match="telegram unavailable"):
            await miniapp_api.miniapp_publish(request)
        async with sessions() as session:
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_poster_upload_rejects_invalid_content_type_before_telegram(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2200, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Poster", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        part = SimpleNamespace(name="poster", headers={"Content-Type": "text/html"})
        request = _Request(show_id=show_id, user_id=owner_id)
        request.multipart = AsyncMock(return_value=SimpleNamespace(next=AsyncMock(return_value=part)))
        with pytest.raises(web.HTTPBadRequest) as error:
            await miniapp_api.miniapp_upload_poster(request)
        assert json.loads(error.value.text) == {"error": "unsupported_poster_type"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_can_manage_venues_and_ad_channels(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=2300, role=UserRole.admin)
            session.add(admin); await session.commit(); admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"name": "Venue", "city": "City", "mapsUrl": "https://maps.example/v", "defaultSeats": 25})
        venue_id = json.loads((await miniapp_api.miniapp_create_venue(request)).text)["id"]
        request.match_info = {"venue_id": str(venue_id)}; request._body = {"name": "Updated", "defaultSeats": 30}
        assert (await miniapp_api.miniapp_update_venue(request)).status == 200
        async with sessions() as session:
            venue = await miniapp_api.crud.get_venue(session, venue_id)
            assert (venue.name, venue.default_seats) == ("Updated", 30)
        assert (await miniapp_api.miniapp_delete_venue(request)).status == 200

        request.match_info = {}; request._body = {"username": "@promo_channel"}
        channel_id = json.loads((await miniapp_api.miniapp_create_ad_channel(request)).text)["id"]
        request.match_info = {"channel_id": str(channel_id)}
        toggled = json.loads((await miniapp_api.miniapp_toggle_ad_channel(request)).text)
        assert toggled["isActive"] is False
        assert (await miniapp_api.miniapp_delete_ad_channel(request)).status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_mutations_validate_show_and_capacity(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2400, role=UserRole.organizer)
            viewer = User(telegram_id=2401)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Capacity", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=2, creator_id=owner.id)
            session.add(show); await session.flush()
            registration = Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=0)
            manual = ManualAttendee(show_id=show.id, name="Manual")
            session.add_all([registration, manual]); await session.commit()
            show_id, owner_id, registration_id, manual_id = show.id, owner.id, registration.id, manual.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        request = _Request(show_id=show_id, user_id=owner_id, body={"guests": 1})
        request.match_info["registration_id"] = str(registration_id)
        with pytest.raises(web.HTTPConflict):
            await miniapp_api.miniapp_update_registration(request)
        request._body = {"checkedInCount": 1}
        assert (await miniapp_api.miniapp_update_registration(request)).status == 200

        request.match_info = {"show_id": str(show_id), "attendee_id": str(manual_id)}
        request._body = {"checkedInCount": 1}
        assert (await miniapp_api.miniapp_update_manual_attendee(request)).status == 200
        assert (await miniapp_api.miniapp_delete_manual_attendee(request)).status == 200

        request.match_info = {"show_id": str(show_id), "registration_id": str(registration_id)}
        assert (await miniapp_api.miniapp_cancel_registration(request)).status == 200
    finally:
        await engine.dispose()
