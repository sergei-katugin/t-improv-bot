from __future__ import annotations

import re
from html import escape


def normalize_telegram_username(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned == "@":
        return None

    cleaned = cleaned.split("?", 1)[0].split("#", 1)[0].strip("/")
    if cleaned.startswith("https://t.me/") or cleaned.startswith("http://t.me/"):
        cleaned = cleaned.split("t.me/", 1)[1]
    cleaned = cleaned.lstrip("@").strip()
    if not cleaned or "/" in cleaned or " " in cleaned:
        return None
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", cleaned):
        return None
    return cleaned.lower()


def normalize_telegram_username_list(raw: str | None) -> list[str] | None:
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"[,;\n]+", raw) if part.strip()]
    usernames: list[str] = []
    for part in parts:
        username = normalize_telegram_username(part)
        if username is None:
            return None
        if username not in usernames:
            usernames.append(username)
    return usernames


def serialize_telegram_usernames(usernames: list[str]) -> str | None:
    return ", ".join(f"@{username}" for username in usernames) or None


def render_telegram_username_list(raw: str | None) -> str:
    if not raw:
        return "не указаны"
    usernames = normalize_telegram_username_list(raw)
    if usernames is None:
        # Keep legacy free-form member lists readable.
        return escape(raw)
    return ", ".join(
        f'<a href="https://t.me/{username}">@{username}</a>' for username in usernames
    )
