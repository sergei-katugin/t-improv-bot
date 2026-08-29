from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiohttp import web

from main import build_webhook_app, get_webhook_secret
from config import settings


def _payload(update_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_700_000_000,
            "text": "/start",
            "chat": {"id": 10, "type": "private"},
            "from": {"id": 10, "is_bot": False, "first_name": "Test"},
        },
    }


class _Request:
    def __init__(self, payload, secret: str | None = None):
        self._payload = payload
        self.headers = {} if secret is None else {"X-Telegram-Bot-Api-Secret-Token": secret}

    async def json(self):
        return self._payload


def _handler(app, path: str):
    return next(
        route.handler for route in app.router.routes()
        if route.method == "POST" and route.resource.canonical == path
    )


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_secret():
    admin_bot = Bot("123456:ADMIN_TEST")
    public_bot = Bot("654321:PUBLIC_TEST")
    app = await build_webhook_app(admin_bot, public_bot, AsyncMock(), AsyncMock())
    try:
        with pytest.raises(web.HTTPUnauthorized):
            await _handler(app, "/telegram/public")(_Request(_payload(1)))
    finally:
        await admin_bot.session.close()
        await public_bot.session.close()


@pytest.mark.asyncio
async def test_webhook_responds_before_background_processing_finishes():
    admin_bot = Bot("123456:ADMIN_TEST")
    public_bot = Bot("654321:PUBLIC_TEST")
    release = asyncio.Event()
    started = asyncio.Event()

    async def feed_webhook_update(**kwargs):
        started.set()
        await release.wait()

    public_dp = AsyncMock()
    public_dp.feed_webhook_update.side_effect = feed_webhook_update
    app = await build_webhook_app(admin_bot, public_bot, AsyncMock(), public_dp)
    try:
        response = await _handler(app, "/telegram/public")(
            _Request(_payload(2), get_webhook_secret(settings.PUBLIC_BOT_TOKEN))
        )
        assert response.status == 200
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not release.is_set()
    finally:
        release.set()
        for callback in app.on_cleanup:
            await callback(app)
        await admin_bot.session.close()
        await public_bot.session.close()
