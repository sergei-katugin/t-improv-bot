from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import settings
from db.models import Show
from time_utils import format_local, utc_to_local
from public_bot.callbacks import (
    ShowCb, RegisterCb, ConfirmRegCb, CancelRegCb,
    EditGuestsCb, GuestsCb, GuestsCustomCb, RemindToggleCb, AttendanceCb,
    CalendarCb, FeedbackCb,
)


def shows_list_kb(shows: list[Show], registered_ids: set[int] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for show in shows:
        date_str = format_local(show.show_date, "%d.%m.%Y")
        mark = "✅ " if registered_ids and show.id in registered_ids else ""
        builder.button(
            text=f"{mark}🎭 {show.title} ({show.team_name}) — {date_str}",
            callback_data=ShowCb(show_id=show.id).pack(),
        )
    builder.button(text="🔍 Фильтр по городу", callback_data="pub_filter_city")
    builder.button(text="🏛 Фильтр по площадке", callback_data="pub_filter_venue")
    builder.adjust(1)
    return builder.as_markup()


def show_detail_kb(show_id: int, is_registered: bool, seats_left: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_registered:
        builder.button(text="📅 Добавить в календарь", callback_data=CalendarCb(show_id=show_id).pack())
        builder.button(text="👥 Изменить кол-во гостей", callback_data=EditGuestsCb(show_id=show_id).pack())
        builder.button(text="❌ Отменить запись", callback_data=CancelRegCb(show_id=show_id).pack())
    elif seats_left > 0:
        builder.button(text="✅ Записаться", callback_data=RegisterCb(show_id=show_id).pack())
    else:
        builder.button(text="😔 Мест нет", callback_data="pub_no_seats")
    builder.button(text="◀️ Назад к списку", callback_data="pub_shows_list")
    builder.adjust(1)
    return builder.as_markup()


def guests_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Только я",      callback_data=GuestsCb(show_id=show_id, guests=0).pack())
    builder.button(text="+1",            callback_data=GuestsCb(show_id=show_id, guests=1).pack())
    builder.button(text="+2",            callback_data=GuestsCb(show_id=show_id, guests=2).pack())
    builder.button(text="✏️ Свой вариант", callback_data=GuestsCustomCb(show_id=show_id).pack())
    builder.adjust(3, 1)
    return builder.as_markup()


def confirm_registration_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=ConfirmRegCb(show_id=show_id).pack())
    builder.button(text="✏️ Изменить имя", callback_data=RegisterCb(show_id=show_id).pack())
    builder.button(text="❌ Отмена",       callback_data=ShowCb(show_id=show_id).pack())
    builder.adjust(2, 1)
    return builder.as_markup()


def reminder_prefs_kb(
    show_id: int,
    remind_7d: bool,
    remind_2d: bool,
    remind_1d: bool,
) -> InlineKeyboardMarkup:
    def icon(v: bool) -> str:
        return "✅" if v else "☐"
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{icon(remind_7d)} За неделю",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_7d", value=int(not remind_7d)).pack(),
    )
    builder.button(
        text=f"{icon(remind_2d)} За два дня",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_2d", value=int(not remind_2d)).pack(),
    )
    builder.button(
        text=f"{icon(remind_1d)} За день",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_1d", value=int(not remind_1d)).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def attendance_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Приду!", callback_data=AttendanceCb(show_id=show_id, action="yes").pack())
    builder.button(text="❌ Не смогу", callback_data=AttendanceCb(show_id=show_id, action="no").pack())
    builder.button(text="👥 Изменить состав", callback_data=AttendanceCb(show_id=show_id, action="guests").pack())
    builder.adjust(2, 1)
    return builder.as_markup()


def calendar_kb(show) -> InlineKeyboardMarkup:
    from datetime import timedelta
    from urllib.parse import urlencode

    local_start = utc_to_local(show.show_date)
    end = local_start + timedelta(hours=2)
    params = urlencode({
        "action": "TEMPLATE",
        "text": show.title,
        "dates": f"{local_start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}",
        "ctz": settings.APP_TIMEZONE,
        "location": f"{show.location}, {show.city}",
        "details": show.poster_text or "Импровизационное шоу",
    })
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Google Calendar", url=f"https://calendar.google.com/calendar/render?{params}")
    builder.button(text="📎 Apple / Outlook (.ics)", callback_data=CalendarCb(show_id=show.id).pack())
    if show.location_url:
        builder.button(text="🗺 Построить маршрут", url=show.location_url)
    builder.adjust(1)
    return builder.as_markup()


def feedback_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for rating in range(1, 6):
        builder.button(text=f"{rating} ⭐", callback_data=FeedbackCb(show_id=show_id, rating=rating).pack())
    builder.adjust(5)
    return builder.as_markup()


def my_shows_kb(registrations) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reg in registrations:
        date_str = format_local(reg.show.show_date, "%d.%m.%Y")
        guests = getattr(reg, "guests", 0) or 0
        suffix = f" ({1 + guests} чел.)" if guests > 0 else ""
        builder.button(
            text=f"✅ {reg.show.title} — {date_str}{suffix}",
            callback_data=ShowCb(show_id=reg.show_id).pack(),
        )
    builder.adjust(1)
    return builder.as_markup()
