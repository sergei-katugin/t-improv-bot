from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import urlparse

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import selectinload

from admin_bot.security import can_manage_owned
from admin_bot.telegram_usernames import (
    normalize_telegram_username, normalize_telegram_username_list,
    serialize_telegram_usernames,
)
from config import ADMIN_ID_LIST, settings
from db import crud
from db.base import AsyncSessionLocal
from db.models import AnnouncementLog, AuditLog, ManualAttendee, Registration, Show, ShowFeedback, User, UserRole, WaitlistEntry
from html_utils import h
from telegram_delivery import send_with_retry
from time_utils import format_local, local_naive_to_utc, utc_now, utc_to_local


MINIAPP_DIST = Path(__file__).with_name("miniapp") / "dist"
ADMIN_BOT_KEY = web.AppKey("miniapp_admin_bot", Bot)
PUBLIC_BOT_KEY = web.AppKey("miniapp_public_bot", Bot)
MINIAPP_RATE_LIMITER_KEY = web.AppKey("miniapp_rate_limiter", object)
MINIAPP_AUTH_CONCURRENCY_KEY = web.AppKey("miniapp_auth_concurrency", asyncio.Semaphore)
MINIAPP_CONCURRENCY_KEY = web.AppKey("miniapp_concurrency", asyncio.Semaphore)
MINIAPP_UPLOAD_CONCURRENCY_KEY = web.AppKey("miniapp_upload_concurrency", asyncio.Semaphore)
MAX_INIT_DATA_AGE_SECONDS = 15 * 60
MAX_SHOWS_PER_PAGE = 100
MAX_POSTER_BYTES = 6 * 1024 * 1024
MAX_POSTER_PIXELS = 16_000_000
REANNOUNCEMENT_WINDOW = timedelta(days=3)
REANNOUNCEMENT_OCCUPANCY_THRESHOLD = 0.5
logger = logging.getLogger(__name__)



__all__ = [name for name in globals() if not name.startswith("__")]
