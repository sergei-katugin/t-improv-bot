from app_logging import get_project_logger
from html_utils import h


logger = get_project_logger(__name__)


async def notify_manual_registration(
    bot, show, *, name: str, contact: str, guests: int, occupied: int,
    automatic: bool,
) -> None:
    if not getattr(show, "registration_chat_id", None):
        return
    reminder = (
        "автоматические напоминания" if automatic else
        "попробуем отправить автоматически; при ошибке сообщим здесь"
    )
    try:
        await bot.send_message(
            show.registration_chat_id,
            f"➕ <b>Добавлена запись вручную</b>\n"
            f"🎭 {h(show.title)}\n"
            f"Полное имя: <b>{h(name)}</b>\n"
            f"Связь: {h(contact)}\n"
            f"Мест в записи: {1 + guests}\n"
            f"Напоминания: {reminder}\n"
            f"Заполнено: <b>{occupied} / {show.max_seats}</b>",
        )
    except Exception:
        logger.exception("failed to notify registration chat about manual entry show_id=%s", show.id)
