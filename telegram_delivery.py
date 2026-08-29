from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from aiogram.exceptions import TelegramRetryAfter


T = TypeVar("T")


async def send_with_retry(send: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
    """Honor Telegram flood-control responses instead of dropping the notification."""
    try:
        result = await send(*args, **kwargs)
    except TelegramRetryAfter as exc:
        await asyncio.sleep(max(0, exc.retry_after) + 0.1)
        result = await send(*args, **kwargs)
    await asyncio.sleep(0.04)  # keep sequential broadcasts below 30 messages/second
    return result
