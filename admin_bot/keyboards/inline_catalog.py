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

__all__ = ['organizers_list_kb', 'fsm_cancel_kb', 'fsm_skip_cancel_kb', 'settings_kb', 'ad_channels_list_kb', 'roles_menu_kb', 'city_kb', 'venue_kb', 'venues_list_kb', 'venue_detail_kb', 'team_kb', 'team_select_kb', 'team_create_fsm_skip_kb', 'teams_list_kb', 'team_detail_kb']


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
