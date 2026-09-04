from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db.models import Show, UserRole
from time_utils import format_local, utc_now
from admin_bot.callbacks import (
    AdminShowActionCb, AdminShowFieldCb, AdminCheckinCb, AdminManualCheckinCb, AdminPartyCountCb,
    AdminTeamActionCb, AdminTeamFieldCb,
    AdminVenueActionCb, AdminVenueFieldCb,
    AdminAdChannelCb, AdminRevokeCb, AdminFilterStatusCb,
    CityCb, VenueCb, TeamCb,
)


def _show_status_icon(show: Show) -> str:
    if not show.is_active:
        return "🚫"
    if show.show_date < utc_now():
        return "✔️"
    return "🎭"


def shows_list_kb(
    shows: list[Show],
    filter_label: str = "",
    can_manage: bool = True,
    *,
    page: int = 0,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for show in shows:
        date_str = format_local(show.show_date, "%d.%m.%Y")
        icon = _show_status_icon(show)
        builder.button(
            text=f"{icon} {show.title} ({show.team_name}) — {date_str}",
            callback_data=AdminShowActionCb(action="open", show_id=show.id).pack(),
        )
    if page > 0:
        builder.button(text="◀️", callback_data=f"admin_shows_page:{page - 1}")
    if has_next:
        builder.button(text="▶️", callback_data=f"admin_shows_page:{page + 1}")
    builder.button(text="🆕 Создать", callback_data="admin_create_show")
    builder.button(text="🔍 Фильтр", callback_data="admin_shows_filter")
    builder.adjust(1)
    return builder.as_markup()


def shows_filter_kb(current: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    status = current.get("status") or "active"
    status_labels = {"all": "Все", "active": "Активные", "cancelled": "Отменённые", "past": "Прошедшие"}
    next_status = {"all": "active", "active": "past", "past": "cancelled", "cancelled": "all"}
    builder.button(
        text=f"Статус: {status_labels[status]}",
        callback_data=AdminFilterStatusCb(status=next_status[status]).pack(),
    )

    team = current.get("team") or "Все команды"
    builder.button(text=f"Команда: {team}", callback_data="admin_filter_team")

    year = current.get("year") or "Все годы"
    builder.button(text=f"Год: {year}", callback_data="admin_filter_year")

    builder.button(text="✅ Применить", callback_data="admin_shows_list")
    builder.button(text="🔄 Сбросить", callback_data="admin_filter_reset")
    builder.adjust(1)
    return builder.as_markup()


def show_detail_kb(show: Show, is_creator_or_admin: bool, can_delete: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Записи", callback_data=AdminShowActionCb(action="regs", show_id=show.id).pack())
    if is_creator_or_admin:
        builder.button(text="🧭 Задачи", callback_data=AdminShowActionCb(action="tasks", show_id=show.id).pack())
        builder.button(text="📄 Создать похожее", callback_data=AdminShowActionCb(action="clone", show_id=show.id).pack())
        builder.button(text="✏️ Редактировать", callback_data=AdminShowActionCb(action="edit", show_id=show.id).pack())
        builder.button(text="📣 Продвижение", callback_data=AdminShowActionCb(action="promotion", show_id=show.id).pack())
        builder.button(text="📊 Аналитика", callback_data=AdminShowActionCb(action="audience", show_id=show.id).pack())
        builder.button(text="⚙️ Настройки шоу", callback_data=AdminShowActionCb(action="show_settings", show_id=show.id).pack())
    builder.button(text="◀️ К списку шоу", callback_data="admin_shows_list")
    builder.adjust(2, 1, 1, 1)
    return builder.as_markup()


def show_section_kb(show: Show, section: str, can_delete: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    show_id = show.id
    if section == "promotion":
        builder.button(text="👁 Превью анонса", callback_data=AdminShowActionCb(action="preview", show_id=show_id).pack())
        if not show.announcement_logs:
            builder.button(text="📢 Отправить анонс", callback_data=AdminShowActionCb(action="announce", show_id=show_id).pack())
        builder.button(text="📱 QR для Instagram", callback_data=AdminShowActionCb(action="qr", show_id=show_id).pack())
        builder.button(text="🔗 Ссылка", callback_data=AdminShowActionCb(action="link", show_id=show_id).pack())
        builder.button(text="🔔 Напомнить зрителям", callback_data=AdminShowActionCb(action="remind", show_id=show_id).pack())
        builder.button(text="📣 Бесплатная реклама", callback_data=AdminShowActionCb(action="free_ad", show_id=show_id).pack())
    elif section == "audience":
        builder.button(text="📈 Показать статистику", callback_data=AdminShowActionCb(action="analytics", show_id=show_id).pack())
        builder.button(text="📥 Скачать список зрителей", callback_data=AdminShowActionCb(action="export", show_id=show_id).pack())
    elif section == "show_settings":
        if show.checkin_enabled:
            builder.button(text="✅ Отметить пришедших", callback_data=AdminShowActionCb(action="checkin", show_id=show_id).pack())
            builder.button(text="🚪 Доступ сотруднику входа", callback_data=AdminShowActionCb(action="checkin_invite", show_id=show_id).pack())
        if show.creator:
            creator_url = f"https://t.me/{show.creator.username}" if show.creator.username else f"tg://user?id={show.creator.telegram_id}"
            builder.button(text="✉️ Написать создателю", url=creator_url)
        builder.button(text=f"🎟 Режим входа: {'вкл' if show.checkin_enabled else 'выкл'}", callback_data=AdminShowActionCb(action="toggle_checkin", show_id=show_id).pack())
        builder.button(text=f"⭐ Отзывы: {'вкл' if show.feedback_enabled else 'выкл'}", callback_data=AdminShowActionCb(action="toggle_feedback", show_id=show_id).pack())
        builder.button(text="⚠️ Управление шоу", callback_data=AdminShowActionCb(action="danger", show_id=show_id).pack())
    else:
        if show.is_active:
            builder.button(text="🚫 Отменить шоу", callback_data=AdminShowActionCb(action="cancel", show_id=show_id).pack())
            if can_delete:
                builder.button(text="🗑 Удалить шоу", callback_data=AdminShowActionCb(action="delete", show_id=show_id).pack())
        else:
            builder.button(text="↩️ Восстановить шоу", callback_data=AdminShowActionCb(action="restore", show_id=show_id).pack())
    back_action = "show_settings" if section == "danger" else "open"
    back_text = "◀️ К настройкам" if section == "danger" else "◀️ К шоу"
    builder.button(text=back_text, callback_data=AdminShowActionCb(action=back_action, show_id=show_id).pack())
    builder.adjust(2)
    return builder.as_markup()


def edit_notification_mode_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔔 С уведомлениями", callback_data=AdminShowActionCb(action="edit_notify", show_id=show_id).pack())
    builder.button(text="🤫 Скрытое обновление", callback_data=AdminShowActionCb(action="edit_silent", show_id=show_id).pack())
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    builder.adjust(1)
    return builder.as_markup()


def checkin_kb(show_id: int, registrations, manual_attendees=()) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Найти по имени", callback_data=AdminShowActionCb(action="checkin_search", show_id=show_id).pack())
    for reg in registrations:
        if reg.is_cancelled:
            continue
        actual = reg.checked_in_count or 0
        mark = "✅" if actual else "⬜️"
        party = 1 + (reg.guests or 0)
        builder.button(
            text=f"{mark} {reg.attendee_name} — {actual}/{party}",
            callback_data=AdminCheckinCb(show_id=show_id, registration_id=reg.id).pack(),
        )
    for attendee in manual_attendees:
        actual = attendee.checked_in_count or 0
        mark = "✅" if actual else "⬜️"
        builder.button(
            text=f"{mark} {attendee.name} — {actual}/1 [вручную]",
            callback_data=AdminManualCheckinCb(show_id=show_id, attendee_id=attendee.id).pack(),
        )
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    builder.adjust(1)
    return builder.as_markup()


def checkin_mode_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 По имени", callback_data=AdminShowActionCb(action="checkin_named", show_id=show_id).pack())
    builder.button(text="🔢 Простой счётчик", callback_data=AdminShowActionCb(action="checkin_counter", show_id=show_id).pack())
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    builder.adjust(1)
    return builder.as_markup()


def checkin_counter_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, action in (("+1", "count_add1"), ("+5", "count_add5"), ("−1", "count_sub1")):
        builder.button(text=label, callback_data=AdminShowActionCb(action=action, show_id=show_id).pack())
    builder.button(text="🔄 Выбрать режим", callback_data=AdminShowActionCb(action="checkin", show_id=show_id).pack())
    builder.adjust(3, 1)
    return builder.as_markup()


def party_count_kb(show_id: int, kind: str, item_id: int, booked: int, current: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    upper = max(booked + 2, current + 1, 5)
    for count in range(0, upper + 1):
        builder.button(
            text=(f"✅ {count}" if count == booked else str(count)),
            callback_data=AdminPartyCountCb(show_id=show_id, kind=kind, item_id=item_id, count=count).pack(),
        )
    builder.button(text="◀️ К списку", callback_data=AdminShowActionCb(action="checkin_named", show_id=show_id).pack())
    builder.adjust(4)
    return builder.as_markup()


def show_created_kb(show_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👁 Проверить превью",  callback_data=AdminShowActionCb(action="preview", show_id=show_id).pack())
    builder.button(text="📢 Отправить анонс",   callback_data=AdminShowActionCb(action="announce", show_id=show_id).pack())
    builder.button(text="🔗 Получить ссылку",   callback_data=AdminShowActionCb(action="link", show_id=show_id).pack())
    builder.button(text="✏️ Редактировать",     callback_data=AdminShowActionCb(action="edit", show_id=show_id).pack())
    builder.button(text="🔔 Подключить чат записей", callback_data=AdminShowActionCb(action="reg_chat", show_id=show_id).pack())
    builder.button(text="◀️ К шоу",             callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def edit_show_fields_kb(show: Show, group: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    show_id = show.id
    groups = {
        "main": [
            ("🎭 Основное", "group_basic"), ("📍 Место и вместимость", "group_venue"),
            ("📝 Афиша", "group_poster"), ("👥 Записи", "group_registration"),
            ("⚙️ Дополнительно", "group_extra"),
        ],
        "basic": [("Название", "title"), ("Команда", "team_name"), ("Дата и время", "show_date")],
        "venue": [("Площадка", "location"), ("Ссылка на карты", "location_url"), ("Город", "city"), ("Количество мест", "max_seats")],
        "poster": [("Текст афиши", "poster_text"), ("Изображение", "poster_file_id")],
        "registration": [("Ответственный за записи", "registrar_id")],
        "extra": [],
    }
    current_group = group or "main"
    fields = groups[current_group]
    for label, field in fields:
        builder.button(text=label, callback_data=AdminShowFieldCb(show_id=show_id, field=field).pack())
    if current_group == "extra":
        builder.button(text=f"🎟 Режим входа: {'вкл' if show.checkin_enabled else 'выкл'}", callback_data=AdminShowFieldCb(show_id=show_id, field="checkin_enabled").pack())
        builder.button(text=f"⭐ Отзывы: {'вкл' if show.feedback_enabled else 'выкл'}", callback_data=AdminShowFieldCb(show_id=show_id, field="feedback_enabled").pack())
    if current_group == "registration":
        builder.button(
            text=f"🔔 Чат записей: {'подключён' if show.registration_chat_id else 'не подключён'}",
            callback_data=AdminShowActionCb(action="reg_chat", show_id=show_id).pack(),
        )
    if current_group == "main":
        builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
        builder.adjust(1)
    else:
        builder.button(text="◀️ К разделам", callback_data=AdminShowFieldCb(show_id=show_id, field="group_main").pack())
        builder.adjust(2)
    return builder.as_markup()


def registrations_kb(show_id: int, manual_attendees=None, can_manage: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if can_manage:
        builder.button(text="➕ Добавить вручную", callback_data=AdminShowActionCb(action="add_manual", show_id=show_id).pack())
        builder.button(text="🔔 Чат записей", callback_data=AdminShowActionCb(action="reg_chat", show_id=show_id).pack())
        if manual_attendees:
            builder.button(text="🗑 Удалить вручную", callback_data=AdminShowActionCb(action="del_manual", show_id=show_id).pack())
    builder.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    builder.adjust(1)
    return builder.as_markup()


def registration_chat_kb(show_id: int, configured: bool, name_mode: str = "short") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if configured:
        builder.button(
            text=f"👤 Имена: {'полностью' if name_mode == 'full' else 'сокращённо'}",
            callback_data=AdminShowActionCb(
                action="reg_name_short" if name_mode == "full" else "reg_name_full", show_id=show_id,
            ).pack(),
        )
        builder.button(
            text="🔌 Отключить чат",
            callback_data=AdminShowActionCb(action="reg_chat_clear", show_id=show_id).pack(),
        )
    builder.button(
        text="◀️ К записям",
        callback_data=AdminShowActionCb(action="regs", show_id=show_id).pack(),
    )
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb(yes_data: str, no_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=yes_data)
    builder.button(text="❌ Отмена",      callback_data=no_data)
    builder.adjust(2)
    return builder.as_markup()


def confirm_with_back_kb(
    yes_data: str,
    no_data: str,
    *,
    checkin_enabled: bool = False,
    feedback_enabled: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=f"🎟 Режим входа: {'вкл' if checkin_enabled else 'выкл'}",
        callback_data="create_toggle_checkin",
    )
    builder.button(
        text=f"⭐ Отзывы: {'вкл' if feedback_enabled else 'выкл'}",
        callback_data="create_toggle_feedback",
    )
    builder.button(text="✅ Создать шоу", callback_data=yes_data)
    builder.button(text="◀️ Назад",       callback_data="fsm_back")
    builder.button(text="❌ Отмена",      callback_data=no_data)
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def organizers_list_kb(organizers) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in organizers:
        name = user.first_name or user.username or str(user.telegram_id)
        if user.role == UserRole.admin:
            builder.button(text=f"👑 {name}", callback_data="admin_noop")
        else:
            builder.button(text=f"❌ {name}", callback_data=AdminRevokeCb(telegram_id=user.telegram_id).pack())
    builder.button(text="◀️ Назад", callback_data="admin_roles_menu")
    builder.adjust(1)
    return builder.as_markup()


def fsm_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data="fsm_back")
    builder.button(text="❌ Отмена", callback_data="fsm_cancel")
    builder.adjust(2)
    return builder.as_markup()


def fsm_skip_cancel_kb(skip_data: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data=skip_data)
    builder.button(text="◀️ Назад",     callback_data="fsm_back")
    builder.button(text="❌ Отмена",     callback_data="fsm_cancel")
    builder.adjust(2, 1)
    return builder.as_markup()


def settings_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Команды",  callback_data="admin_teams_list")
    builder.button(text="ℹ️ Инфо",    callback_data="settings_info")
    if is_admin:
        builder.button(text="👥 Управление доступом", callback_data="admin_roles_menu")
        builder.button(text="🏛 Площадки",            callback_data="admin_venues_list")
        builder.button(text="📣 Рекламные каналы",    callback_data="admin_adchannels_list")
    builder.adjust(2)
    return builder.as_markup()


def ad_channels_list_kb(channels) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        icon = "🟢" if ch.is_active else "🔴"
        builder.button(
            text=f"{icon} {ch.username}",
            callback_data=AdminAdChannelCb(action="toggle", channel_id=ch.id).pack(),
        )
        builder.button(
            text="🗑",
            callback_data=AdminAdChannelCb(action="delete", channel_id=ch.id).pack(),
        )
    builder.button(text="➕ Добавить канал", callback_data="admin_adchannel_add")
    builder.button(text="◀️ К настройкам",   callback_data="admin_settings")
    builder.adjust(2)  # icon+username | 🗑 per row
    # last two buttons full-width
    n = len(channels)
    if n:
        builder.adjust(*([2] * n), 1, 1)
    else:
        builder.adjust(1, 1)
    return builder.as_markup()


def roles_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Выдать доступ",    callback_data="admin_grant_organizer")
    builder.button(text="👥 Список с доступом", callback_data="admin_list_organizers")
    builder.adjust(1)
    return builder.as_markup()


def city_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙 Лимасол",       callback_data=CityCb(value="Лимасол").pack())
    builder.button(text="🏙 Никосия",       callback_data=CityCb(value="Никосия").pack())
    builder.button(text="🏙 Пафос",         callback_data=CityCb(value="Пафос").pack())
    builder.button(text="✏️ Свой вариант",  callback_data=CityCb(value="custom").pack())
    builder.button(text="❌ Отмена",         callback_data="fsm_cancel")
    builder.adjust(1)
    return builder.as_markup()


def venue_kb(venues: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for v in venues:
        builder.button(text=f"🎭 {v.name}", callback_data=VenueCb(venue_id=v.id).pack())
    builder.button(text="✏️ Свой вариант", callback_data=VenueCb(venue_id=0).pack())
    builder.button(text="❌ Отмена",        callback_data="fsm_cancel")
    builder.adjust(1)
    return builder.as_markup()


def venues_list_kb(venues: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for v in venues:
        icon = "🎭" if v.is_active else "🚫"
        builder.button(
            text=f"{icon} {v.name} · {v.default_seats} мест",
            callback_data=AdminVenueActionCb(action="open", venue_id=v.id).pack(),
        )
    builder.button(text="➕ Добавить площадку", callback_data="admin_venue_add")
    builder.button(text="🏠 Главное меню",       callback_data="admin_back_main")
    builder.adjust(1)
    return builder.as_markup()


def venue_detail_kb(venue) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Название",     callback_data=AdminVenueFieldCb(venue_id=venue.id, field="name").pack())
    builder.button(text="🏙 Город",        callback_data=AdminVenueFieldCb(venue_id=venue.id, field="city").pack())
    builder.button(text="🪑 Мест",         callback_data=AdminVenueFieldCb(venue_id=venue.id, field="default_seats").pack())
    builder.button(text="🗺 Ссылка карты", callback_data=AdminVenueFieldCb(venue_id=venue.id, field="maps_url").pack())
    toggle_text = "🚫 Скрыть" if venue.is_active else "✅ Показать"
    builder.button(text=toggle_text, callback_data=AdminVenueFieldCb(venue_id=venue.id, field="toggle").pack())
    builder.button(text="🗑 Удалить",      callback_data=AdminVenueFieldCb(venue_id=venue.id, field="delete").pack())
    builder.button(text="◀️ К площадкам",  callback_data="admin_venues_list")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


# ─── Teams ────────────────────────────────────────────────────────────────────

def team_kb() -> InlineKeyboardMarkup:
    """Compact entry point for team step in show creation FSM."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Выбрать команду", callback_data="team_show_existing")
    builder.button(text="➕ Создать команду",  callback_data="team_create_from_fsm")
    builder.button(text="✏️ Ввести вручную",  callback_data=TeamCb(team_id=0).pack())
    builder.button(text="❌ Отмена",          callback_data="fsm_cancel")
    builder.adjust(2, 2)
    return builder.as_markup()


def team_select_kb(
    teams: list, *, back_callback: str = "team_back_to_entry", back_text: str = "◀️ К выбору команды"
) -> InlineKeyboardMarkup:
    """Full team list shown after clicking 'Выбрать команду'."""
    builder = InlineKeyboardBuilder()
    for t in teams:
        builder.button(text=f"🎭 {t.name}", callback_data=TeamCb(team_id=t.id).pack())
    builder.button(text=back_text, callback_data=back_callback)
    builder.adjust(2)
    return builder.as_markup()


def team_create_fsm_skip_kb() -> InlineKeyboardMarkup:
    """Used in inline team creation: skip members step, then return to show FSM."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data="team_fsm_skip_members")
    builder.button(text="❌ Отмена",     callback_data="team_fsm_cancel_create")
    builder.adjust(2)
    return builder.as_markup()


def teams_list_kb(teams: list) -> InlineKeyboardMarkup:
    """Team management list (admin sees all, viewer sees own)."""
    builder = InlineKeyboardBuilder()
    for t in teams:
        icon = "🎭" if t.is_active else "🚫"
        builder.button(
            text=f"{icon} {t.name}",
            callback_data=AdminTeamActionCb(action="open", team_id=t.id).pack(),
        )
    builder.button(text="➕ Создать команду", callback_data="admin_team_add")
    builder.button(text="🏠 Главное меню",     callback_data="admin_back_main")
    builder.adjust(1)
    return builder.as_markup()


def team_detail_kb(team, can_manage: bool) -> InlineKeyboardMarkup:
    """Detail view: edit name/members, toggle active, delete (only for owner/admin)."""
    builder = InlineKeyboardBuilder()
    if can_manage:
        builder.button(text="✏️ Название",  callback_data=AdminTeamFieldCb(team_id=team.id, field="name").pack())
        builder.button(text="👥 Участники", callback_data=AdminTeamFieldCb(team_id=team.id, field="members").pack())
        toggle_text = "🚫 Скрыть" if team.is_active else "✅ Показать"
        builder.button(text=toggle_text,    callback_data=AdminTeamFieldCb(team_id=team.id, field="toggle").pack())
        builder.button(text="🗑 Удалить",   callback_data=AdminTeamFieldCb(team_id=team.id, field="delete").pack())
        builder.adjust(2, 2)
    builder.button(text="◀️ К командам", callback_data="admin_teams_list")
    builder.adjust(*(([2, 2] if can_manage else []) + [1]))
    return builder.as_markup()
