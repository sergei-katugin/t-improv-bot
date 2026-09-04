from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import miniapp_api
from db.base import Base
from db.models import AuditLog, AnnouncementLog, ManualAttendee, Registration, Show, ShowFeedback, User, UserRole
from miniapp_api import (
    MiniAppAuthError, _csv_value, _require_admin, _set_miniapp_security_headers,
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


@pytest.mark.parametrize("path,expected_header", [
    ("/api/miniapp/me", ("Cache-Control", "private, no-store")),
    ("/app", ("Content-Security-Policy", "default-src 'self'")),
])
def test_miniapp_security_headers(path, expected_header):
    request = type("Request", (), {"path": path})()
    response = web.Response()

    _set_miniapp_security_headers(request, response)

    name, expected = expected_header
    assert expected in response.headers[name]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"


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
