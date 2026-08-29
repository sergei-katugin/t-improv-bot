from datetime import date, datetime

import pytest
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base
from db.fsm_storage import SQLAlchemyStorage
import db.fsm_storage as fsm_module


@pytest.mark.asyncio
async def test_fsm_upsert_preserves_state_and_serializes_data(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(fsm_module, "AsyncSessionLocal", sessions)
        storage = SQLAlchemyStorage()
        key = StorageKey(bot_id=1, chat_id=2, user_id=3)
        payload = {"day": date(2026, 8, 29), "at": datetime(2026, 8, 29, 19, 30)}

        await storage.set_state(key, "registration:name")
        await storage.set_data(key, payload)

        assert await storage.get_state(key) == "registration:name"
        assert await storage.get_data(key) == payload
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fsm_keys_are_isolated_by_bot_and_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(fsm_module, "AsyncSessionLocal", sessions)
        storage = SQLAlchemyStorage()
        first = StorageKey(bot_id=1, chat_id=10, user_id=20)
        second = StorageKey(bot_id=2, chat_id=10, user_id=20)

        await storage.set_state(first, "first")

        assert await storage.get_state(first) == "first"
        assert await storage.get_state(second) is None
    finally:
        await engine.dispose()
