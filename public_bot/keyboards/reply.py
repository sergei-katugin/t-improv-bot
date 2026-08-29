from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb(has_shows: bool = True, has_regs: bool = False) -> ReplyKeyboardMarkup:
    # Keep the two useful entry points stable: Telegram clients may retain an
    # older reply keyboard after registration until the bot sends a new one.
    _ = has_shows, has_regs
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🎭 Все шоу"), KeyboardButton(text="📋 Мои записи")]],
        resize_keyboard=True,
        persistent=True,
    )
