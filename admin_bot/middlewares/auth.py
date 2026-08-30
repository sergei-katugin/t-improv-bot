from typing import Any, Callable, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from config import ADMIN_ID_LIST
from db.base import AsyncSessionLocal
from db import crud
from db.models import UserRole


class AdminAuthMiddleware(BaseMiddleware):
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

        telegram_id = tg_user.id

        if telegram_id in ADMIN_ID_LIST:
            data["is_super_admin"] = True
            async with AsyncSessionLocal() as session:
                data["db_user"] = await crud.upsert_user(
                    session,
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name,
                    last_name=tg_user.last_name,
                )
                data["session"] = session
                # Do not keep a checked-out connection while the handler waits
                # for Telegram network calls. The session can acquire a new one
                # lazily when the handler performs its next database operation.
                await session.commit()
                return await handler(event, data)

        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_telegram_id(session, telegram_id)
            if user and (
                user.role in (UserRole.admin, UserRole.organizer)
                or await crud.has_any_checkin_access(session, user.id)
            ):
                data["is_super_admin"] = user.role == UserRole.admin
                data["db_user"] = user
                data["session"] = session
                await session.commit()
                return await handler(event, data)

        if isinstance(event, Message):
            await event.answer("⛔ Доступ запрещён.")
        elif isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ запрещён.", show_alert=True)
