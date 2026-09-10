from __future__ import annotations

import hashlib
import hmac
import json
import base64
import sys
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import miniapp_api
from admin_bot.keyboards import reply as reply_keyboards
from db.base import Base
from db import crud
from db.models import AuditLog, AnnouncementLog, ManualAttendee, Registration, Show, ShowFeedback, User, UserRole
from miniapp_api import (
    MiniAppAuthError, _audit_details, _csv_value, _require_admin, _set_miniapp_security_headers,
    _show_fields, miniapp_auth_concurrency_middleware, miniapp_request_logging_middleware,
    validate_telegram_init_data,
)
from time_utils import utc_now


BOT_TOKEN = "123456:MINIAPP_TEST_TOKEN"
NOW = 1_800_000_000




def _signed_init_data(*, auth_date: int = NOW, user_id: int = 42, extra=None) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(
            {"id": user_id, "first_name": "Sergey", "username": "sergey"},
            separators=(",", ":"),
        ),
    }
    fields.update(extra or {})
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


def _valid_show_payload():
    return {
        "title": "Новое шоу", "teamName": "T·IMPRO", "showDateLocal": "2099-09-05T20:00",
        "location": "Театр", "locationUrl": "https://maps.example/venue", "city": "Лимасол",
        "posterText": "Текст", "maxSeats": 50, "registrarUsername": "@sergey",
        "checkinEnabled": True, "feedbackEnabled": True,
    }


class _Request(dict):
    def __init__(self, *, show_id: int, user_id: int, is_admin: bool = False, body=None):
        super().__init__(miniapp_user_id=user_id, miniapp_is_admin=is_admin)
        self.match_info = {"show_id": str(show_id)}
        self.query = {}
        self.content_length = None
        self._body = body

    async def json(self):
        return self._body

__all__ = [name for name in globals() if not name.startswith("__")]
