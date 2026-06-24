from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📋 Афиша"),  KeyboardButton(text="🆕 Создать")],
        [KeyboardButton(text="🎭 Моё"),    KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, persistent=True)


remove_kb = ReplyKeyboardRemove()
