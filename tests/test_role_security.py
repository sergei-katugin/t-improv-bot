from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from admin_bot.handlers import roles
from db.models import UserRole


@pytest.mark.asyncio
async def test_admin_role_cannot_be_revoked_via_forged_callback(monkeypatch):
    actor = SimpleNamespace(id=1, telegram_id=100, role=UserRole.admin)
    target = SimpleNamespace(id=2, telegram_id=200, role=UserRole.admin)
    callback = SimpleNamespace(
        answer=AsyncMock(), from_user=SimpleNamespace(id=100),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    session = AsyncMock()
    monkeypatch.setattr(roles.crud, "get_user_by_telegram_id", AsyncMock(return_value=target))
    set_role = AsyncMock()
    monkeypatch.setattr(roles.crud, "set_user_role", set_role)

    await roles.revoke_viewer(
        callback, SimpleNamespace(telegram_id=200), session, db_user=actor,
    )

    set_role.assert_not_awaited()
    assert callback.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_organizer_role_can_still_be_revoked(monkeypatch):
    actor = SimpleNamespace(id=1, telegram_id=100, role=UserRole.admin)
    target = SimpleNamespace(id=2, telegram_id=200, role=UserRole.organizer, first_name="User", username=None)
    callback = SimpleNamespace(
        answer=AsyncMock(), from_user=SimpleNamespace(id=100),
        message=SimpleNamespace(edit_text=AsyncMock()),
    )
    session = AsyncMock()
    monkeypatch.setattr(roles.crud, "get_user_by_telegram_id", AsyncMock(return_value=target))
    set_role = AsyncMock(return_value=target)
    monkeypatch.setattr(roles.crud, "set_user_role", set_role)

    await roles.revoke_viewer(
        callback, SimpleNamespace(telegram_id=200), session, db_user=actor,
    )

    set_role.assert_awaited_once_with(session, 200, UserRole.user)
