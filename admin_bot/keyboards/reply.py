from aiogram.types import (
    ChatAdministratorRights, KeyboardButton, KeyboardButtonRequestChat,
    ReplyKeyboardMarkup, ReplyKeyboardRemove,
)


def main_menu_kb() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="📋 Афиша"),  KeyboardButton(text="🆕 Создать")],
        [KeyboardButton(text="🎭 Моё"),    KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, persistent=True)


def shows_context_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Создать"), KeyboardButton(text="🎭 Моё")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🏠 Главное меню")],
        ], resize_keyboard=True, persistent=True,
    )


def show_context_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👥 Записи"), KeyboardButton(text="✏️ Редактировать")],
            [KeyboardButton(text="📣 Продвижение"), KeyboardButton(text="◀️ К списку шоу")],
        ], resize_keyboard=True, persistent=True,
    )


def promotion_context_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👁 Превью"), KeyboardButton(text="📢 Анонс")],
            [KeyboardButton(text="🔗 Ссылка и QR"), KeyboardButton(text="◀️ К шоу")],
        ], resize_keyboard=True, persistent=True,
    )


def registrations_context_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить зрителя"), KeyboardButton(text="🔔 Чат записей")],
            [KeyboardButton(text="🎟 Режим входа"), KeyboardButton(text="◀️ К шоу")],
        ], resize_keyboard=True, persistent=True,
    )


def flow_context_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена"), KeyboardButton(text="🏠 Главное меню")]],
        resize_keyboard=True, persistent=True,
    )


def registration_channel_picker_kb() -> ReplyKeyboardMarkup:
    no_rights = dict(
        is_anonymous=False, can_manage_chat=False, can_delete_messages=False,
        can_manage_video_chats=False, can_restrict_members=False,
        can_promote_members=False, can_change_info=False, can_invite_users=False,
        can_post_stories=False, can_edit_stories=False, can_delete_stories=False,
    )
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📣 Выбрать канал",
                request_chat=KeyboardButtonRequestChat(
                    request_id=7101,
                    chat_is_channel=True,
                    user_administrator_rights=ChatAdministratorRights(**no_rights),
                    bot_administrator_rights=ChatAdministratorRights(
                        **no_rights, can_post_messages=True,
                    ),
                    request_title=True,
                    request_username=True,
                ),
            )],
            [KeyboardButton(text="⏭ Пропустить")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def settings_context_kb(is_admin: bool) -> ReplyKeyboardMarkup:
    buttons = [KeyboardButton(text="👥 Команды")]
    if is_admin:
        buttons.extend([
            KeyboardButton(text="🏛 Площадки"), KeyboardButton(text="👥 Управление доступом"),
        ])
    buttons.append(KeyboardButton(text="🏠 Главное меню"))
    rows = [buttons[index:index + 2] for index in range(0, len(buttons), 2)]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, persistent=True)


remove_kb = ReplyKeyboardRemove()
