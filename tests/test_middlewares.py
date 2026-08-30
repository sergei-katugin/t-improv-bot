from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin_bot.middlewares.auth import AdminAuthMiddleware
import admin_bot.middlewares.auth as admin_auth_module
from db.base import Base
from db.models import User, UserRole
from public_bot.middlewares.user_context import UserContextMiddleware
import public_bot.middlewares.user_context as user_context_module


def _message(telegram_id: int) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(timezone.utc),
        chat=Chat(id=telegram_id, type="private"),
        from_user=TelegramUser(id=telegram_id, is_bot=False, first_name="Test"),
        text="hello",
    )


@pytest.mark.asyncio
async def test_public_middleware_releases_transaction_before_handler(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(user_context_module, "AsyncSessionLocal", sessions)

        async def handler(event, data):
            assert not data["session"].in_transaction()
            assert data["db_user"].telegram_id == 101
            assert "menu_kb" in data
            return "handled"

        result = await UserContextMiddleware()(handler, _message(101), {})
        assert result == "handled"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_middleware_allows_super_admin_without_open_transaction(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(admin_auth_module, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(admin_auth_module, "ADMIN_ID_LIST", [202])

        async def handler(event, data):
            assert data["is_super_admin"] is True
            assert not data["session"].in_transaction()
            return "handled"

        assert await AdminAuthMiddleware()(handler, _message(202), {}) == "handled"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_middleware_allows_organizer_and_denies_regular_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(admin_auth_module, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(admin_auth_module, "ADMIN_ID_LIST", [])
        async with sessions() as session:
            session.add_all([
                User(telegram_id=303, first_name="Org", role=UserRole.organizer),
                User(telegram_id=404, first_name="Viewer", role=UserRole.user),
            ])
            await session.commit()

        handler = AsyncMock(return_value="allowed")
        assert await AdminAuthMiddleware()(handler, _message(303), {}) == "allowed"
        allowed_data = handler.await_args.args[1]
        assert allowed_data["is_super_admin"] is False
        assert not allowed_data["session"].in_transaction()

        denied = _message(404)
        answer = AsyncMock()
        monkeypatch.setattr(Message, "answer", answer)
        assert await AdminAuthMiddleware()(handler, denied, {}) is None
        assert handler.await_count == 1
        answer.assert_awaited_once()
    finally:
        await engine.dispose()
