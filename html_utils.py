from __future__ import annotations

from html import escape


def h(value) -> str:
    """Escape untrusted values before inserting them into Telegram HTML messages."""
    return escape(str(value), quote=True)
