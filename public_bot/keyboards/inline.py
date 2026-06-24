from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db.models import Show
from public_bot.callbacks import (
    ShowCb, RegisterCb, ConfirmRegCb, CancelRegCb,
    EditGuestsCb, GuestsCb, GuestsCustomCb, RemindToggleCb,
)


def shows_list_kb(shows: list[Show], registered_ids: set[int] = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for show in shows:
        date_str = show.show_date.strftime("%d.%m.%Y")
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


def reminder_prefs_kb(show_id: int, remind_14d: bool, remind_7d: bool, remind_1d: bool) -> InlineKeyboardMarkup:
    def icon(v: bool) -> str:
        return "✅" if v else "☐"
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"{icon(remind_14d)} За 2 недели",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_14d", value=int(not remind_14d)).pack(),
    )
    builder.button(
        text=f"{icon(remind_7d)} За 1 неделю",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_7d", value=int(not remind_7d)).pack(),
    )
    builder.button(
        text=f"{icon(remind_1d)} За 1 день",
        callback_data=RemindToggleCb(show_id=show_id, field="remind_1d", value=int(not remind_1d)).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def my_shows_kb(registrations) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for reg in registrations:
        date_str = reg.show.show_date.strftime("%d.%m.%Y")
        guests = getattr(reg, "guests", 0) or 0
        suffix = f" ({1 + guests} чел.)" if guests > 0 else ""
        builder.button(
            text=f"✅ {reg.show.title} — {date_str}{suffix}",
            callback_data=ShowCb(show_id=reg.show_id).pack(),
        )
    builder.adjust(1)
    return builder.as_markup()
