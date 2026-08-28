from __future__ import annotations

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def main_menu_kb(has_shows: bool = True, has_regs: bool = False) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    buttons = []
    if has_shows:
        buttons.append(KeyboardButton(text="🎭 Шоу"))
    if has_regs:
        buttons.append(KeyboardButton(text="📋 Мои записи"))
    if not buttons:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[buttons],
        resize_keyboard=True,
        persistent=True,
    )
