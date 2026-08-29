import logging
import time
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings

# SQLite needs `check_same_thread` connect arg; other drivers (asyncpg) do not.
raw_db_url = settings.DATABASE_URL
# Normalize common Postgres URL schemes to the SQLAlchemy asyncpg form
# so code works even if the environment provides `postgres://` or `postgresql://`.
if raw_db_url.startswith("postgres://"):
    db_url = raw_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif raw_db_url.startswith("postgresql://") and "+asyncpg" not in raw_db_url:
    db_url = raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    db_url = raw_db_url

is_sqlite = db_url.startswith("sqlite") or "sqlite+" in db_url
connect_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_async_engine(
    db_url,
    echo=False,
    connect_args=connect_args,
)

sql_query_count: ContextVar[int] = ContextVar("sql_query_count", default=0)
_sql_logger = logging.getLogger(__name__)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    context._query_started_at = time.monotonic()
    sql_query_count.set(sql_query_count.get() + 1)


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    elapsed_ms = (time.monotonic() - context._query_started_at) * 1000
    if elapsed_ms >= 100:
        _sql_logger.warning("Slow SQL query duration_ms=%.1f", elapsed_ms)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
