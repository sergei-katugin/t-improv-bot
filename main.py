from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys

from app_logging import PROJECT_LOG_PREFIX, get_project_logger, install_project_logging

install_project_logging()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent, Update
from aiohttp import web

from config import settings

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


root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
handler.setFormatter(TaggedFormatter(fmt))
root_logger.handlers = [handler]

logger = get_project_logger(__name__)


# Note: alembic migrations are intentionally not run automatically here.


async def register_commands(admin_bot: Bot, public_bot: Bot) -> None:
    await admin_bot.set_my_commands([
        BotCommand(command="home",        description="Главное меню"),
        BotCommand(command="shows",       description="Список шоу"),
        BotCommand(command="my",          description="Мои шоу"),
        BotCommand(command="create_show", description="Создать шоу"),
        BotCommand(command="settings",    description="Настройки"),
        BotCommand(command="teams",       description="Команды"),
        BotCommand(command="venues",      description="Площадки"),
        BotCommand(command="roles",       description="Управление доступом"),
        BotCommand(command="info",        description="Справка"),
    ])
    await public_bot.set_my_commands([
        BotCommand(command="start",    description="Главная"),
        BotCommand(command="shows",    description="Все предстоящие шоу"),
        BotCommand(command="my_shows", description="Мои записи"),
    ])


def get_webhook_base_url() -> str:
    base_url = settings.WEBHOOK_BASE_URL or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("PUBLIC_URL")
    if not base_url:
        raise RuntimeError("WEBHOOK_BASE_URL or RENDER_EXTERNAL_URL/PUBLIC_URL is required for webhook mode")
    return base_url.rstrip("/")


async def build_webhook_app(admin_bot: Bot, public_bot: Bot, admin_dp: Dispatcher, public_dp: Dispatcher) -> web.Application:
    app = web.Application()

    async def health_handler(request):
        return web.Response(text="ok")

    async def admin_webhook_handler(request):
        payload = await request.json()
        await admin_dp.feed_webhook_update(bot=admin_bot, update=Update(**payload))
        return web.Response(status=200)

    async def public_webhook_handler(request):
        payload = await request.json()
        await public_dp.feed_webhook_update(bot=public_bot, update=Update(**payload))
        return web.Response(status=200)

    app.router.add_get("/health", health_handler)
    app.router.add_post("/telegram/admin", admin_webhook_handler)
    app.router.add_post("/telegram/public", public_webhook_handler)
    return app


async def on_error(event: ErrorEvent):
    exc = event.exception
    msg = str(exc)
    if any(s in msg for s in ("query is too old", "query ID is invalid", "message is not modified")):
        return
    logger.error("Unhandled error: %s", exc, exc_info=exc)


def build_admin_bot() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.ADMIN_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
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
    dp = Dispatcher()
    dp.message.outer_middleware(UserContextMiddleware())
    dp.callback_query.outer_middleware(UserContextMiddleware())
    dp.errors.register(on_error)
    dp.include_router(start.router)
    dp.include_router(shows.router)
    dp.include_router(registration.router)
    dp.include_router(my_shows.router)
    return bot, dp


async def main():
    from db.base import AsyncSessionLocal
    from db import crud as _crud
    async with AsyncSessionLocal() as session:
        try:
            await _crud.seed_venues(session)
        except Exception as e:
            logger.warning("Skipping seed_venues: %s", e)

    admin_bot, admin_dp = build_admin_bot()
    public_bot, public_dp = build_public_bot()

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

    async def _configure_webhooks_with_retries(
        admin_bot: Bot, public_bot: Bot, admin_url: str, public_url: str, max_attempts: int = 5
    ) -> None:
        logger.info("Configuring webhooks: admin=%s public=%s", admin_url, public_url)
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            try:
                await admin_bot.delete_webhook(drop_pending_updates=True)
                await public_bot.delete_webhook(drop_pending_updates=True)
                await admin_bot.set_webhook(
                    url=admin_url,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True,
                )
                await public_bot.set_webhook(
                    url=public_url,
                    allowed_updates=["message", "callback_query"],
                    drop_pending_updates=True,
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

    await stop_event.wait()

    logger.info("Останавливаю webhook-сервер...")
    await admin_bot.delete_webhook(drop_pending_updates=True)
    await public_bot.delete_webhook(drop_pending_updates=True)

    scheduler.shutdown(wait=False)
    await runner.cleanup()
    await admin_bot.session.close()
    await public_bot.session.close()
    logger.info("Боты остановлены.")


if __name__ == "__main__":
    asyncio.run(main())
