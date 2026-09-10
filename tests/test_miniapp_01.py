import asyncio

from tests.miniapp_support import *


def test_miniapp_accepts_valid_telegram_signature():
    user = validate_telegram_init_data(_signed_init_data(), BOT_TOKEN, now=NOW)

    assert user.telegram_id == 42
    assert user.username == "sergey"
    assert user.first_name == "Sergey"


def test_miniapp_rejects_tampered_user():
    init_data = _signed_init_data().replace("%3A42", "%3A43")

    with pytest.raises(MiniAppAuthError, match="signature"):
        validate_telegram_init_data(init_data, BOT_TOKEN, now=NOW)


@pytest.mark.parametrize("auth_date", [NOW - 901, NOW + 31])
def test_miniapp_rejects_expired_or_future_auth_data(auth_date):
    with pytest.raises(MiniAppAuthError, match="expired"):
        validate_telegram_init_data(_signed_init_data(auth_date=auth_date), BOT_TOKEN, now=NOW)


def test_miniapp_accepts_init_data_at_replay_window_boundary():
    assert validate_telegram_init_data(
        _signed_init_data(auth_date=NOW - 900), BOT_TOKEN, now=NOW,
    ).telegram_id == 42


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


def test_miniapp_show_payload_is_normalized_and_whitelisted():
    fields = _show_fields(_valid_show_payload(), require_all=True)

    assert fields["team_name"] == "T·IMPRO"
    assert fields["registrar_username"] == "sergey"
    assert fields["max_seats"] == 50
    assert fields["max_guests"] == 6
    assert fields["registration_closes_at"] == fields["show_date"] - timedelta(minutes=5)

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


def test_miniapp_admin_resources_require_admin_role():
    with pytest.raises(web.HTTPForbidden):
        _require_admin({"miniapp_is_admin": False})
    _require_admin({"miniapp_is_admin": True})


@pytest.mark.asyncio
async def test_miniapp_rate_limit_uses_authenticated_user_and_retry_after(monkeypatch):
    request = type(
        "Request", (dict,), {"path": "/api/miniapp/shows/1/poster", "method": "POST"},
    )(miniapp_user_id=42)
    request.app = {
        miniapp_api.MINIAPP_RATE_LIMITER_KEY: miniapp_api.MiniAppRateLimiter(),
        miniapp_api.MINIAPP_CONCURRENCY_KEY: __import__("asyncio").Semaphore(1),
        miniapp_api.MINIAPP_UPLOAD_CONCURRENCY_KEY: __import__("asyncio").Semaphore(1),
    }
    monkeypatch.setattr(miniapp_api.time, "monotonic", lambda: 100.0)
    handler = AsyncMock(return_value=web.json_response({"ok": True}))

    for _ in range(3):
        assert (await miniapp_api.miniapp_rate_limit_middleware(request, handler)).status == 200
    with pytest.raises(web.HTTPTooManyRequests) as exc_info:
        await miniapp_api.miniapp_rate_limit_middleware(request, handler)
    assert exc_info.value.headers["Retry-After"] == "60"
    assert json.loads(exc_info.value.text)["bucket"] == "poster_upload"


def test_miniapp_rate_policies_prioritize_expensive_operations():
    request = SimpleNamespace(path="/api/miniapp/shows/1/publish", method="POST")
    assert miniapp_api._miniapp_rate_policy(request) == ("telegram_send", 5, 60)
    request.path = "/api/miniapp/shows/1/export.csv"; request.method = "GET"
    assert miniapp_api._miniapp_rate_policy(request) == ("csv_export", 5, 60)
    request.path = "/api/miniapp/shows"; request.method = "PATCH"
    assert miniapp_api._miniapp_rate_policy(request) == ("mutation", 30, 60)
    request.method = "GET"
    assert miniapp_api._miniapp_rate_policy(request) is None


@pytest.mark.asyncio
async def test_miniapp_auth_concurrency_is_released_after_request():
    request = type("Request", (dict,), {"path": "/api/miniapp/me"})()
    semaphore = __import__("asyncio").Semaphore(1)
    request.app = {miniapp_api.MINIAPP_AUTH_CONCURRENCY_KEY: semaphore}
    handler = AsyncMock(return_value=web.json_response({"ok": True}))

    response = await miniapp_auth_concurrency_middleware(request, handler)

    assert response.status == 200
    assert not semaphore.locked()


@pytest.mark.asyncio
async def test_miniapp_auth_concurrency_rejects_when_capacity_is_exhausted():
    request = type("Request", (dict,), {"path": "/api/miniapp/me"})()
    request.app = {
        miniapp_api.MINIAPP_AUTH_CONCURRENCY_KEY: __import__("asyncio").Semaphore(0),
    }
    handler = AsyncMock()

    with pytest.raises(web.HTTPServiceUnavailable) as exc_info:
        await miniapp_auth_concurrency_middleware(request, handler)

    assert exc_info.value.headers["Retry-After"] == "1"
    assert json.loads(exc_info.value.text)["error"] == "authentication_capacity_exceeded"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_test_announcement_is_sent_only_to_current_miniapp_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=4242, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Test announcement", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id, poster_text="Text", poster_file_id="saved-poster")
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = AsyncMock()
        request = _Request(show_id=show_id, user_id=owner_id, body={})
        request["miniapp_telegram_id"] = 4242
        request.app = {miniapp_api.ADMIN_BOT_KEY: bot}

        response = await miniapp_api.miniapp_send_test_announcement(request)

        assert response.status == 200
        assert bot.send_photo.await_args.args == (4242, "saved-poster")
        assert "Тестовый анонс" in bot.send_photo.await_args.kwargs["caption"]
        assert bot.send_photo.await_args.kwargs["reply_markup"].inline_keyboard[0][0].url.endswith(f"show_{show_id}")
        bot.send_message.assert_not_awaited()

        async def timeout(_awaitable, timeout):
            assert timeout == 15
            _awaitable.close()
            raise asyncio.TimeoutError

        monkeypatch.setattr(asyncio, "wait_for", timeout)
        with pytest.raises(web.HTTPGatewayTimeout) as error:
            await miniapp_api.miniapp_send_test_announcement(request)
        assert "15 секунд" in json.loads(error.value.text)["message"]
    finally:
        await engine.dispose()


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
    assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
    if path.startswith("/app"):
        assert "object-src 'none'" in response.headers["Content-Security-Policy"]


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
