from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from db.base import AsyncSessionLocal
from db import crud
from public_bot.keyboards.reply import main_menu_kb


class UserContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)):
            tg_user = event.from_user
        else:
            return await handler(event, data)

        async with AsyncSessionLocal() as session:
            db_user = await crud.upsert_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
                last_name=tg_user.last_name,
            )
            data["db_user"] = db_user
            data["session"] = session
            if isinstance(event, Message):
                has_shows, has_regs = await crud.get_menu_flags(session, db_user.id)
                data["menu_kb"] = main_menu_kb(
                    has_shows=has_shows,
                    has_regs=has_regs,
                )
            # End the middleware transaction before entering code that can
            # spend seconds waiting for Telegram. expire_on_commit=False keeps
            # db_user usable and the session reconnects lazily when required.
            await session.commit()
            return await handler(event, data)
