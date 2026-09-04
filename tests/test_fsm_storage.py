from datetime import date, datetime, timedelta

import pytest
from aiogram.fsm.storage.base import StorageKey
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import func, select

from db.base import Base
from db.fsm_storage import SQLAlchemyStorage
from db.models import FSMStorageRecord
from time_utils import utc_now
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


@pytest.mark.asyncio
async def test_fsm_clear_deletes_empty_record_but_empty_data_preserves_active_state(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(fsm_module, "AsyncSessionLocal", sessions)
        storage = SQLAlchemyStorage()
        key = StorageKey(bot_id=1, chat_id=2, user_id=3)

        await storage.set_state(key, "registration:name")
        await storage.set_data(key, {})
        assert await storage.get_state(key) == "registration:name"

        await storage.set_state(key, None)
        await storage.set_data(key, {})

        async with sessions() as session:
            count = await session.scalar(select(func.count()).select_from(FSMStorageRecord))
        assert count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_fsm_cleanup_deletes_only_stale_records(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(fsm_module, "AsyncSessionLocal", sessions)
        storage = SQLAlchemyStorage()
        stale = StorageKey(bot_id=1, chat_id=1, user_id=1)
        fresh = StorageKey(bot_id=1, chat_id=2, user_id=2)
        await storage.set_state(stale, "old")
        await storage.set_state(fresh, "new")
        async with sessions() as session:
            record = await session.get(FSMStorageRecord, storage._record_key(stale))
            record.updated_at = utc_now() - timedelta(days=31)
            await session.commit()

        assert await storage.cleanup_stale(30) == 1
        assert await storage.get_state(stale) is None
        assert await storage.get_state(fresh) == "new"
    finally:
        await engine.dispose()
