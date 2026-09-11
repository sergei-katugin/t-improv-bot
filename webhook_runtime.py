from __future__ import annotations

import asyncio
import hashlib
import os
import re
import secrets
import time
from collections.abc import Awaitable
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonWebApp, Update, WebAppInfo
from aiohttp import web

from app_logging import get_project_logger
from config import settings
from miniapp_api import ADMIN_BOT_KEY, PUBLIC_BOT_KEY, register_miniapp_routes

logger = get_project_logger(__name__)


async def _best_effort_telegram_setup(label: str, action: Awaitable[Any]) -> None:
    """Keep optional Telegram metadata failures from stopping the web server."""
    try:
        await action
    except Exception:
        logger.exception("Telegram startup setup failed step=%s; continuing", label)


def get_webhook_secret(bot_token: str) -> str:
    """Return the configured secret, with a safe no-config fallback.

    Existing Render services may not receive a newly-added Blueprint variable
    until it is configured in the dashboard. Deriving a secret from the bot
    token keeps those deployments authenticated during that transition.
    """
    if settings.REQUIRE_WEBHOOK_SECRET and not settings.WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is required in this environment")
    if settings.WEBHOOK_SECRET:
        configured = settings.WEBHOOK_SECRET.strip()
        if settings.REQUIRE_WEBHOOK_SECRET and len(configured) < 32:
            raise RuntimeError("WEBHOOK_SECRET must contain at least 32 characters")
        if configured and len(configured) <= 256 and re.fullmatch(r"[A-Za-z0-9_-]+", configured):
            return configured
        logger.warning(
            "WEBHOOK_SECRET contains characters unsupported by Telegram; using its SHA-256 digest"
        )
        return hashlib.sha256(settings.WEBHOOK_SECRET.encode()).hexdigest()
    return hashlib.sha256(bot_token.encode()).hexdigest()


async def register_commands(admin_bot: Bot, public_bot: Bot) -> None:
    # Telegram uses the bot's display name as the native Mini App header title.
    # The Mini App JavaScript API cannot change that title per route.
    await _best_effort_telegram_setup(
        "admin_name", admin_bot.set_my_name(name=settings.ADMIN_BOT_DISPLAY_NAME)
    )
    await _best_effort_telegram_setup("admin_commands", admin_bot.set_my_commands([
        BotCommand(command="start",       description="Начать работу"),
        BotCommand(command="home",        description="Главное меню"),
        BotCommand(command="shows",       description="Список шоу"),
        BotCommand(command="my",          description="Мои шоу"),
        BotCommand(command="app",         description="Открыть Mini App"),
        BotCommand(command="help",        description="Справка"),
        BotCommand(command="privacy",     description="Конфиденциальность"),
    ]))
    await _best_effort_telegram_setup("public_commands", public_bot.set_my_commands([
        BotCommand(command="start",    description="Главная"),
        BotCommand(command="shows",    description="Все предстоящие шоу"),
        BotCommand(command="my_shows", description="Мои записи"),
        BotCommand(command="help",     description="Помощь"),
        BotCommand(command="settings", description="Настройки"),
        BotCommand(command="privacy",  description="Конфиденциальность"),
        BotCommand(command="delete_me", description="Удалить мои данные"),
    ]))
    from admin_bot.keyboards.reply import _miniapp_url
    miniapp_url = _miniapp_url()
    if miniapp_url:
        await _best_effort_telegram_setup("admin_menu_button", admin_bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="Открыть Mini App",
            web_app=WebAppInfo(url=miniapp_url),
        )))
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
