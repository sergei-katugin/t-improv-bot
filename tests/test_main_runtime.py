from __future__ import annotations

import hashlib
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

import main
from config import settings


def _route(app: web.Application, method: str, path: str):
    return next(
        route.handler
        for route in app.router.routes()
        if route.method == method and route.resource.canonical == path
    )


def test_runtime_formatters_and_health_filter(monkeypatch):
    formatter = main.TaggedFormatter("%(message)s")
    assert formatter.format(logging.LogRecord("aiohttp.access", 20, "", 0, "request", (), None)) == "[HTTP] request"
    assert formatter.format(logging.LogRecord("scheduler.jobs", 20, "", 0, "job", (), None)) == "[BOT] job"
    project = logging.LogRecord("library", 20, "", 0, "ours", (), None)
    project.project_prefix = True
    assert formatter.format(project).startswith(main.PROJECT_LOG_PREFIX)
    assert formatter.format(logging.LogRecord("library", 20, "", 0, "plain", (), None)) == "plain"

    health_filter = main.HealthCheckLogFilter(interval_seconds=60)
    ordinary = logging.LogRecord("aiohttp.access", 20, "", 0, '"GET /other HTTP/1.1" 200 ', (), None)
    health = logging.LogRecord("aiohttp.access", 20, "", 0, '"GET /health HTTP/1.1" 200 ', (), None)
    assert health_filter.filter(ordinary)
    monkeypatch.setattr(main.time, "monotonic", lambda: 100.0)
    assert health_filter.filter(health)
    assert not health_filter.filter(health)
    monkeypatch.setattr(main.time, "monotonic", lambda: 161.0)
    assert health_filter.filter(health)


def test_runtime_webhook_secret_fallback_and_base_url(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "")
    assert main.get_webhook_secret("token") == hashlib.sha256(b"token").hexdigest()

    monkeypatch.setattr(settings, "WEBHOOK_BASE_URL", "https://example.test/")
    assert main.get_webhook_base_url() == "https://example.test"
    monkeypatch.setattr(settings, "WEBHOOK_BASE_URL", "")
    monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)
    monkeypatch.setenv("PUBLIC_URL", "https://public.test/")
    assert main.get_webhook_base_url() == "https://public.test"
    monkeypatch.delenv("PUBLIC_URL")
    with pytest.raises(RuntimeError, match="WEBHOOK_BASE_URL"):
        main.get_webhook_base_url()


@pytest.mark.asyncio
async def test_register_commands_configures_name_commands_and_menu(monkeypatch):
    admin_bot = AsyncMock()
    public_bot = AsyncMock()
    monkeypatch.setattr("admin_bot.keyboards.reply._miniapp_url", lambda: "https://example.test/app")

    await main.register_commands(admin_bot, public_bot)

    admin_bot.set_my_name.assert_awaited_once_with(name=settings.ADMIN_BOT_DISPLAY_NAME)
    admin_bot.set_my_commands.assert_awaited_once()
    public_bot.set_my_commands.assert_awaited_once()
    menu = admin_bot.set_chat_menu_button.await_args.kwargs["menu_button"]
    assert menu.text == "Открыть Mini App"
    assert menu.web_app.url == "https://example.test/app"

    admin_bot.reset_mock()
    monkeypatch.setattr("admin_bot.keyboards.reply._miniapp_url", lambda: None)
    await main.register_commands(admin_bot, public_bot)
    admin_bot.set_chat_menu_button.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_commands_survives_telegram_setup_rate_limit(monkeypatch):
    admin_bot = AsyncMock()
    public_bot = AsyncMock()
    admin_bot.set_my_name.side_effect = RuntimeError("retry after 58779")
    monkeypatch.setattr("admin_bot.keyboards.reply._miniapp_url", lambda: "https://example.test/app")

    await main.register_commands(admin_bot, public_bot)

    admin_bot.set_my_commands.assert_awaited_once()
    public_bot.set_my_commands.assert_awaited_once()
    admin_bot.set_chat_menu_button.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_error_handler_ignores_stale_callbacks_and_alerts(monkeypatch):
    bot = AsyncMock()
    await main.on_error(SimpleNamespace(exception=RuntimeError("query is too old")), bot)
    bot.send_message.assert_not_awaited()

    monkeypatch.setattr(settings, "ERROR_ALERT_CHAT_ID", 123)
    await main.on_error(SimpleNamespace(exception=ValueError("bad <value>")), bot)
    message = bot.send_message.await_args.args[1]
    assert "ValueError" in message
    assert "&lt;value&gt;" in message

    bot.send_message.side_effect = RuntimeError("telegram unavailable")
    await main.on_error(SimpleNamespace(exception=ValueError("again")), bot)


@pytest.mark.asyncio
async def test_webhook_health_readiness_and_admin_dispatch(monkeypatch):
    admin_bot = AsyncMock()
    public_bot = AsyncMock()
    admin_dp = AsyncMock()
    public_dp = AsyncMock()
    app = await main.build_webhook_app(admin_bot, public_bot, admin_dp, public_dp)

    health = await _route(app, "GET", "/health")(SimpleNamespace())
    assert health.status == 200 and health.text == "ok"

    connection = AsyncMock()
    context = AsyncMock()
    context.__aenter__.return_value = connection
    fake_engine = SimpleNamespace(connect=lambda: context)
    monkeypatch.setattr("db.base.engine", fake_engine)
    ready = await _route(app, "GET", "/ready")(SimpleNamespace())
    assert ready.status == 200
    connection.execute.assert_awaited_once()

    context.__aenter__.side_effect = RuntimeError("db down")
    unavailable = await _route(app, "GET", "/ready")(SimpleNamespace())
    assert unavailable.status == 503

    secret = main.get_webhook_secret(settings.ADMIN_BOT_TOKEN)
    request = SimpleNamespace(
        headers={"X-Telegram-Bot-Api-Secret-Token": secret},
        json=AsyncMock(return_value={"update_id": 99}),
    )
    response = await _route(app, "POST", "/telegram/admin")(request)
    assert response.status == 200
    admin_dp.feed_webhook_update.assert_awaited_once()


def test_bot_builders_register_expected_routers(monkeypatch):
    from aiogram.fsm.storage.memory import MemoryStorage

    monkeypatch.setattr("db.fsm_storage.SQLAlchemyStorage", MemoryStorage)
    admin_bot, admin_dp = main.build_admin_bot()
    public_bot, public_dp = main.build_public_bot()
    try:
        assert len(admin_dp.sub_routers) == 7
        assert len(public_dp.sub_routers) == 4
    finally:
        # Bot sessions have no open connector until a request is made.
        del admin_bot, public_bot


@pytest.mark.asyncio
async def test_main_runs_complete_webhook_lifecycle(monkeypatch):
    admin_bot = AsyncMock()
    public_bot = AsyncMock()

    # Dispatchers support item assignment; this tiny stand-in keeps orchestration isolated.
    class FakeDispatcher(dict):
        def __init__(self):
            super().__init__()
            self.storage = AsyncMock()

    admin_dp = FakeDispatcher()
    public_dp = FakeDispatcher()
    monkeypatch.setattr(main, "build_admin_bot", lambda: (admin_bot, admin_dp))
    monkeypatch.setattr(main, "build_public_bot", lambda: (public_bot, public_dp))
    monkeypatch.setattr(main, "build_webhook_app", AsyncMock(return_value=web.Application()))
    monkeypatch.setattr(main, "register_commands", AsyncMock())
    monkeypatch.setattr(main, "setup_scheduler", lambda *_args: None)
    monkeypatch.setattr(main, "scheduler", SimpleNamespace(running=False))
    monkeypatch.setattr(settings, "WEBHOOK_BASE_URL", "https://bot.example")
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "")

    runner = AsyncMock()
    runner.setup = AsyncMock()
    runner.cleanup = AsyncMock()
    monkeypatch.setattr(main.web, "AppRunner", lambda _app: runner)
    site = AsyncMock()
    site.start = AsyncMock()
    monkeypatch.setattr(main.web, "TCPSite", lambda *_args: site)

    class DoneEvent:
        def set(self): pass
        async def wait(self): return None

    monkeypatch.setattr(main.asyncio, "Event", DoneEvent)
    loop = SimpleNamespace(add_signal_handler=lambda *_args: None)
    monkeypatch.setattr(main.asyncio, "get_running_loop", lambda: loop)

    session = AsyncMock()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    monkeypatch.setattr("db.base.AsyncSessionLocal", lambda: session_context)
    engine = AsyncMock()
    monkeypatch.setattr("db.base.engine", engine)
    monkeypatch.setattr("db.crud.seed_venues", AsyncMock())

    await main.main()

    admin_bot.set_webhook.assert_awaited_once()
    public_bot.set_webhook.assert_awaited_once()
    runner.setup.assert_awaited_once()
    runner.cleanup.assert_awaited_once()
    admin_dp.storage.close.assert_awaited_once()
    public_dp.storage.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()
