from datetime import timedelta
import hashlib

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db import crud
from db.base import Base
from db.models import InviteToken, ManualAttendee, Show, User, UserRole
from time_utils import utc_now


async def _fixture(session):
    creator = User(telegram_id=1001, first_name="Creator")
    viewer = User(telegram_id=1002, first_name="Viewer")
    session.add_all([creator, viewer])
    await session.flush()
    show = Show(
        title="Test", team_name="Team", show_date=utc_now() + timedelta(days=1),
        location="Venue", city="Limassol", max_seats=3, creator_id=creator.id,
    )
    session.add(show)
    await session.commit()
    return creator, viewer, show


__all__ = [name for name in globals() if not name.startswith("__")]
