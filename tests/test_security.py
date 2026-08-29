from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from admin_bot.security import can_manage_owned, is_admin
from admin_bot.handlers.registrations import _csv_cell
from db import crud
from db.base import Base
from db.models import InviteToken, User, UserRole
from html_utils import h
from time_utils import utc_now


def test_admin_can_manage_any_owned_object():
    admin = SimpleNamespace(id=1, role=UserRole.admin)
    assert is_admin(admin)
    assert can_manage_owned(creator_id=999, db_user=admin)


def test_organizer_can_only_manage_own_object():
    organizer = SimpleNamespace(id=10, role=UserRole.organizer)
    assert can_manage_owned(creator_id=10, db_user=organizer)
    assert not can_manage_owned(creator_id=11, db_user=organizer)


def test_user_html_is_escaped_for_telegram_messages():
    assert h('<b title="x">&') == "&lt;b title=&quot;x&quot;&gt;&amp;"


def test_csv_export_neutralizes_spreadsheet_formulas():
    assert _csv_cell("=HYPERLINK(\"https://example.test\")").startswith("'=")
    assert _csv_cell("Normal name") == "Normal name"


@pytest.mark.asyncio
async def test_expired_invite_cannot_be_consumed():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(telegram_id=101, first_name="Viewer")
            session.add(user)
            await session.flush()
            invite = InviteToken(
                token="expired-token",
                role=UserRole.organizer,
                expires_at=utc_now() - timedelta(seconds=1),
            )
            session.add(invite)
            await session.commit()

            consumed = await crud.consume_invite_token(session, invite.token, user.id)

            assert consumed is None
            await session.refresh(user)
            assert user.role == UserRole.user
    finally:
        await engine.dispose()
