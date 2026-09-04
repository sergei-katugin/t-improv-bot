from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import secrets
import signal
import sys
import time

from app_logging import PROJECT_LOG_PREFIX, get_project_logger, install_project_logging

install_project_logging()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent, MenuButtonWebApp, Update, WebAppInfo
from aiohttp import web

from config import settings
from html_utils import h

from admin_bot.middlewares.auth import AdminAuthMiddleware
from admin_bot.handlers import shows as admin_shows
from admin_bot.handlers import registrations as admin_regs
from admin_bot.handlers import roles as admin_roles
from admin_bot.handlers import onboarding as admin_onboarding
from admin_bot.handlers import venues as admin_venues
from admin_bot.handlers import teams as admin_teams
from admin_bot.handlers import ad_channels as admin_ad_channels

from public_bot.middlewares.user_context import UserContextMiddleware
from public_bot.handlers import start, shows, registration, my_shows

from scheduler.jobs import setup_scheduler, scheduler
from miniapp_api import ADMIN_BOT_KEY, PUBLIC_BOT_KEY, register_miniapp_routes


class TaggedFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        name = record.name or ""
        if getattr(record, "project_prefix", ""):
            return f"{PROJECT_LOG_PREFIX} {base}"
        if name.startswith("aiohttp"):
            return "[HTTP] " + base
        if name.startswith(("admin_bot", "public_bot", "scheduler", "db", "aiogram")) or name in ("__main__", __name__):
            return "[BOT] " + base
        return base


class HealthCheckLogFilter(logging.Filter):
    """Keep successful Render health checks visible without flooding the log."""

    def __init__(self, interval_seconds: float = 60.0) -> None:
        super().__init__()
        self.interval_seconds = interval_seconds
        self._last_logged_at: float | None = None

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name != "aiohttp.access":
            return True

        message = record.getMessage()
        is_successful_health_check = '"GET /health HTTP/' in message and '" 200 ' in message
        if not is_successful_health_check:
            return True

        now = time.monotonic()
        if self._last_logged_at is not None and now - self._last_logged_at < self.interval_seconds:
            return False
        self._last_logged_at = now
        return True


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
handler.setFormatter(TaggedFormatter(fmt))
handler.addFilter(HealthCheckLogFilter(interval_seconds=60.0))
root_logger.handlers = [handler]

logger = get_project_logger(__name__)


# Render applies Alembic migrations in its start command before starting this app.


def get_webhook_secret(bot_token: str) -> str:
    """Return the configured secret, with a safe no-config fallback.

    Existing Render services may not receive a newly-added Blueprint variable
    until it is configured in the dashboard. Deriving a secret from the bot
    token keeps those deployments authenticated during that transition.
    """
    if settings.WEBHOOK_SECRET:
        configured = settings.WEBHOOK_SECRET.strip()
        if configured and len(configured) <= 256 and re.fullmatch(r"[A-Za-z0-9_-]+", configured):
            return configured
        logger.warning(
            "WEBHOOK_SECRET contains characters unsupported by Telegram; using its SHA-256 digest"
        )
        return hashlib.sha256(settings.WEBHOOK_SECRET.encode()).hexdigest()
    return hashlib.sha256(bot_token.encode()).hexdigest()


async def register_commands(admin_bot: Bot, public_bot: Bot) -> None:
    await admin_bot.set_my_commands([
        BotCommand(command="start",       description="Начать работу"),
        BotCommand(command="home",        description="Главное меню"),
        BotCommand(command="shows",       description="Список шоу"),
        BotCommand(command="my",          description="Мои шоу"),
        BotCommand(command="create_show", description="Создать шоу"),
        BotCommand(command="settings",    description="Настройки"),
        BotCommand(command="teams",       description="Команды"),
        BotCommand(command="venues",      description="Площадки"),
        BotCommand(command="roles",       description="Управление доступом"),
        BotCommand(command="help",        description="Справка"),
        BotCommand(command="privacy",     description="Конфиденциальность"),
    ])
    await public_bot.set_my_commands([
        BotCommand(command="start",    description="Главная"),
        BotCommand(command="shows",    description="Все предстоящие шоу"),
        BotCommand(command="my_shows", description="Мои записи"),
        BotCommand(command="help",     description="Помощь"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="privacy",  description="Конфиденциальность"),
        BotCommand(command="delete_me", description="Удалить мои данные"),
    ])
    from admin_bot.keyboards.reply import _miniapp_url
    miniapp_url = _miniapp_url()
    if miniapp_url:
        await admin_bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Открыть Mini App",
            web_app=WebAppInfo(url=miniapp_url),
        ))
        logger.info("Admin bot Mini App menu button configured url=%s", miniapp_url)
    else:
        logger.warning("Admin bot Mini App menu button is not configured: public base URL is missing")


def get_webhook_base_url() -> str:
    base_url = settings.WEBHOOK_BASE_URL or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if not base_url:
        raise RuntimeError("WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL/PUBLIC_URL is required for webhook mode")
    return base_url.rstrip("/")


async def build_webhook_app(admin_bot: Bot, public_bot: Bot, admin_dp: Dispatcher, public_dp: Dispatcher) -> web.Application:
    app = web.Application(client_max_size=9 * 1024 * 1024)
    app[ADMIN_BOT_KEY] = admin_bot
    app[PUBLIC_BOT_KEY] = public_bot
    update_slots = asyncio.Semaphore(settings.MAX_CONCURRENT_UPDATES)

    def verify_telegram_secret(request: web.Request, expected_secret: str) -> None:
        supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not secrets.compare_digest(supplied_secret, expected_secret):
            raise web.HTTPUnauthorized(text="Invalid webhook secret")

    async def health_handler(request):
        return web.Response(text="ok")

    async def readiness_handler(request):
        from sqlalchemy import text as sql_text
        from db.base import engine
        try:
            async with engine.connect() as connection:
                await connection.execute(sql_text("SELECT 1"))
        except Exception:
            logger.exception("Readiness database check failed")
            return web.Response(status=503, text="database unavailable")
        return web.Response(text="ready")

    async def process_update(dp: Dispatcher, bot: Bot, update: Update, bot_name: str) -> None:
        from db.base import sql_query_count

        query_token = sql_query_count.set(0)
        started_at = time.monotonic()
        try:
            await dp.feed_webhook_update(bot=bot, update=update)
        finally:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            queries = sql_query_count.get()
            logger.info(
                "Telegram update processed bot=%s update_id=%s duration_ms=%.1f sql_queries=%d",
                bot_name, update.update_id, elapsed_ms, queries,
            )
            sql_query_count.reset(query_token)

    async def dispatch_update(dp: Dispatcher, bot: Bot, update: Update, bot_name: str) -> None:
        # Acknowledge Telegram only after the update has been handled.  Returning
        # 200 before this await would make an update disappear if the process
        # stopped while a background task was still running.
        async with update_slots:
            await process_update(dp, bot, update, bot_name)

    async def admin_webhook_handler(request):
        verify_telegram_secret(request, get_webhook_secret(settings.ADMIN_BOT_TOKEN))
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": admin_bot})
        await dispatch_update(admin_dp, admin_bot, update, "admin")
        return web.Response(status=200)

    async def public_webhook_handler(request):
        verify_telegram_secret(request, get_webhook_secret(settings.PUBLIC_BOT_TOKEN))
        payload = await request.json()
        update = Update.model_validate(payload, context={"bot": public_bot})
        await dispatch_update(public_dp, public_bot, update, "public")
        return web.Response(status=200)

    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", readiness_handler)
    app.router.add_post("/telegram/admin", admin_webhook_handler)
    app.router.add_post("/telegram/public", public_webhook_handler)
    register_miniapp_routes(app)
    return app


async def on_error(event: ErrorEvent, bot: Bot):
    exc = event.exception
    msg = str(exc)
    if any(s in msg for s in ("query is too old", "query ID is invalid", "message is not modified")):
        return
    logger.error("Unhandled error: %s", exc, exc_info=exc)
    if settings.ERROR_ALERT_CHAT_ID:
        try:
            await bot.send_message(
                settings.ERROR_ALERT_CHAT_ID,
                f"🚨 <b>Ошибка бота</b>\n\n<code>{h(type(exc).__name__ + ': ' + msg[:2500])}</code>",
            )
        except Exception:
            logger.exception("Could not deliver error alert")


def build_admin_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.ADMIN_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    from db.fsm_storage import SQLAlchemyStorage
    dp = Dispatcher(storage=SQLAlchemyStorage())
    dp.message.outer_middleware(AdminAuthMiddleware())
    dp.callback_query.outer_middleware(AdminAuthMiddleware())
    dp.errors.register(on_error)
    dp.include_router(admin_onboarding.router)
    dp.include_router(admin_venues.router)
    dp.include_router(admin_teams.router)
    dp.include_router(admin_ad_channels.router)
    dp.include_router(admin_shows.router)
    dp.include_router(admin_regs.router)
    dp.include_router(admin_roles.router)
    return bot, dp


def build_public_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.PUBLIC_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    from db.fsm_storage import SQLAlchemyStorage
    dp = Dispatcher(storage=SQLAlchemyStorage())
    dp.message.outer_middleware(UserContextMiddleware())
    dp.callback_query.outer_middleware(UserContextMiddleware())
    dp.errors.register(on_error)
    dp.include_router(start.router)
    dp.include_router(shows.router)
    dp.include_router(registration.router)
    dp.include_router(my_shows.router)
    return bot, dp


async def main():
    from db.base import AsyncSessionLocal, engine
    from db import crud as _crud
    async with AsyncSessionLocal() as session:
        try:
            await _crud.seed_venues(session)
        except Exception as e:
            logger.warning("Skipping seed_venues: %s", e)

    admin_bot, admin_dp = build_admin_bot()
    public_bot, public_dp = build_public_bot()
    runner: web.AppRunner | None = None

    async def _configure_webhooks_with_retries(
        admin_bot: Bot, public_bot: Bot, admin_url: str, public_url: str, max_attempts: int = 5
    ) -> None:
        logger.info("Configuring webhooks: admin=%s public=%s", admin_url, public_url)
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                await admin_bot.set_webhook(
                    url=admin_url,
                    allowed_updates=["message", "callback_query"],
                    secret_token=get_webhook_secret(settings.ADMIN_BOT_TOKEN),
                )
                await public_bot.set_webhook(
                    url=public_url,
                    allowed_updates=["message", "callback_query"],
                    secret_token=get_webhook_secret(settings.PUBLIC_BOT_TOKEN),
                )
                logger.info("Webhooks configured successfully on attempt %d", attempt)
                return
            except Exception as e:
                logger.warning(
                    "Attempt %d/%d: Failed to configure Telegram webhooks: %s",
                    attempt,
                    max_attempts,
                    e,
                )
                # exponential backoff (in seconds)
                backoff = min(2 ** attempt, 30)
                await asyncio.sleep(backoff)

        logger.error(
            "Could not configure Telegram webhooks after %d attempts; continuing without webhooks",
            max_attempts,
        )

    try:
        if not settings.WEBHOOK_SECRET:
            logger.warning("WEBHOOK_SECRET is not configured; using token-derived secrets")

        base_url = get_webhook_base_url()
        admin_webhook_url = f"{base_url}/telegram/admin"
        public_webhook_url = f"{base_url}/telegram/public"

        app = await build_webhook_app(admin_bot, public_bot, admin_dp, public_dp)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", "8080"))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()

        await register_commands(admin_bot, public_bot)
        setup_scheduler(public_bot, admin_bot)

        logger.info("Computed webhook base URL: %s", base_url)
        await _configure_webhooks_with_retries(admin_bot, public_bot, admin_webhook_url, public_webhook_url)

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def _stop(sig_name: str):
            logger.info("Получен %s — останавливаю...", sig_name)
            stop_event.set()

        loop.add_signal_handler(signal.SIGINT, _stop, "SIGINT")
        loop.add_signal_handler(signal.SIGTERM, _stop, "SIGTERM")

        logger.info("Webhook-боты запущены на %s и %s", admin_webhook_url, public_webhook_url)
        admin_dp["public_bot"] = public_bot
        public_dp["admin_bot"] = admin_bot
        await stop_event.wait()
    finally:
        logger.info("Останавливаю webhook-сервер...")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if runner is not None:
            await runner.cleanup()
        await admin_dp.storage.close()
        await public_dp.storage.close()
        await admin_bot.session.close()
        await public_bot.session.close()
        await engine.dispose()
        logger.info("Боты остановлены.")


if __name__ == "__main__":
    asyncio.run(main())
