import asyncio
import logging
import signal
import subprocess
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent

from config import settings

from admin_bot.middlewares.auth import AdminAuthMiddleware
from admin_bot.handlers import shows as admin_shows
from admin_bot.handlers import registrations as admin_regs
from admin_bot.handlers import roles as admin_roles
from admin_bot.handlers import onboarding as admin_onboarding
from admin_bot.handlers import venues as admin_venues
from admin_bot.handlers import teams as admin_teams

from public_bot.middlewares.user_context import UserContextMiddleware
from public_bot.handlers import start, shows, registration, my_shows

from scheduler.jobs import setup_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_migrations() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
    )
    logger.info("Database migrations applied")


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
        await _crud.seed_venues(session)

    admin_bot, admin_dp = build_admin_bot()
    public_bot, public_dp = build_public_bot()

    await register_commands(admin_bot, public_bot)
    setup_scheduler(public_bot, admin_bot)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _stop(sig_name: str):
        logger.info("Получен %s — останавливаю...", sig_name)
        stop_event.set()

    loop.add_signal_handler(signal.SIGINT, _stop, "SIGINT")
    loop.add_signal_handler(signal.SIGTERM, _stop, "SIGTERM")

    logger.info("Боты запущены. Ctrl+C для остановки.")

    admin_dp["public_bot"] = public_bot

    admin_task = asyncio.create_task(
        admin_dp.start_polling(admin_bot, allowed_updates=["message", "callback_query"], handle_signals=False, drop_pending_updates=True)
    )
    public_task = asyncio.create_task(
        public_dp.start_polling(public_bot, allowed_updates=["message", "callback_query"], handle_signals=False, drop_pending_updates=True)
    )

    await stop_event.wait()

    logger.info("Останавливаю полинг...")
    await admin_dp.stop_polling()
    await public_dp.stop_polling()

    await asyncio.gather(admin_task, public_task, return_exceptions=True)

    scheduler.shutdown(wait=False)
    await admin_bot.session.close()
    await public_bot.session.close()
    logger.info("Боты остановлены.")


if __name__ == "__main__":
    run_migrations()
    asyncio.run(main())
