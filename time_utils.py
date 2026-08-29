from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from config import settings


UTC = timezone.utc
APP_TZ = ZoneInfo(settings.APP_TIMEZONE)


def utc_now() -> datetime:
    """Current UTC time in the naive form used by existing DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_now() -> datetime:
    return datetime.now(APP_TZ)


def local_naive_to_utc(value: datetime) -> datetime:
    """Interpret a naive admin-entered value in the configured local timezone."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(tzinfo=APP_TZ).astimezone(UTC).replace(tzinfo=None)


def utc_to_local(value: datetime) -> datetime:
    """Interpret a naive DB value as UTC and return an aware local datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(APP_TZ)


def local_date(value: datetime) -> date:
    return utc_to_local(value).date()


def format_local(value: datetime, fmt: str = "%d.%m.%Y %H:%M") -> str:
    return utc_to_local(value).strftime(fmt)
