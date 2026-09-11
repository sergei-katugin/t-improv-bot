from __future__ import annotations

from html import escape
import re


def h(value) -> str:
    """Escape untrusted values before inserting them into Telegram HTML messages."""
    return escape(str(value), quote=True)


def formatted_description(value) -> str:
    """Escape description text and allow only **bold** Telegram markup."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", h(value), flags=re.DOTALL)
