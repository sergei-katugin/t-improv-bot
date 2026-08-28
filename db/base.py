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

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
