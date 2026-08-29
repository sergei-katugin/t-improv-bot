"""Postgres/SQLite-backed storage for aiogram FSM state."""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Mapping

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StateType, StorageKey
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db.base import AsyncSessionLocal
from db.models import FSMStorageRecord
from time_utils import utc_now


def _json_default(value: Any) -> dict[str, str]:
    if isinstance(value, datetime):
        return {"__fsm_type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__fsm_type__": "date", "value": value.isoformat()}
    raise TypeError(f"FSM data contains unsupported type: {type(value).__name__}")


def _json_object_hook(value: dict[str, Any]) -> Any:
    value_type = value.get("__fsm_type__")
    if value_type == "datetime":
        return datetime.fromisoformat(value["value"])
    if value_type == "date":
        return date.fromisoformat(value["value"])
    return value


class SQLAlchemyStorage(BaseStorage):
    """Aiogram storage that survives restarts and supports multiple instances.

    A key includes bot, chat and user IDs, so parallel conversations never
    share state. Telegram forum/business fields are included as well.
    """

    @staticmethod
    def _record_key(key: StorageKey) -> tuple[int, int, int, int, str, str]:
        return (
            key.bot_id,
            key.chat_id,
            key.user_id,
            key.thread_id or 0,
            key.business_connection_id or "",
            key.destiny,
        )

    @staticmethod
    def _new_record(record_key: tuple[int, int, int, int, str, str]) -> FSMStorageRecord:
        return FSMStorageRecord(
            bot_id=record_key[0], chat_id=record_key[1], user_id=record_key[2],
            thread_id=record_key[3], business_connection_id=record_key[4],
            destiny=record_key[5],
        )

    @staticmethod
    async def _upsert(session, record_key, field: str, value: Any) -> None:
        key_values = dict(zip(
            ("bot_id", "chat_id", "user_id", "thread_id", "business_connection_id", "destiny"),
            record_key,
        ))
        values = {**key_values, field: value}
        dialect = session.bind.dialect.name
        if dialect == "postgresql":
            statement = pg_insert(FSMStorageRecord).values(**values)
        elif dialect == "sqlite":
            statement = sqlite_insert(FSMStorageRecord).values(**values)
        else:
            record = await session.get(FSMStorageRecord, record_key)
            if record is None:
                record = SQLAlchemyStorage._new_record(record_key)
                session.add(record)
            setattr(record, field, value)
            return
        statement = statement.on_conflict_do_update(
            index_elements=list(key_values),
            set_={field: value, "updated_at": utc_now()},
        )
        await session.execute(statement)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        record_key = self._record_key(key)
        state_value = state.state if isinstance(state, State) else state
        async with AsyncSessionLocal() as session:
            await self._upsert(session, record_key, "state", state_value)
            await session.commit()

    async def get_state(self, key: StorageKey) -> str | None:
        async with AsyncSessionLocal() as session:
            record = await session.get(FSMStorageRecord, self._record_key(key))
            return record.state if record else None

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        record_key = self._record_key(key)
        encoded_data = json.dumps(dict(data), default=_json_default, ensure_ascii=False)
        async with AsyncSessionLocal() as session:
            await self._upsert(session, record_key, "data", encoded_data)
            await session.commit()

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with AsyncSessionLocal() as session:
            record = await session.get(FSMStorageRecord, self._record_key(key))
            return json.loads(record.data, object_hook=_json_object_hook) if record else {}

    async def close(self) -> None:
        # The SQLAlchemy engine is application-wide and closed by main.py.
        return None
