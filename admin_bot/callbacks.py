from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class AdminShowActionCb(CallbackData, prefix="adm_s"):
    action: str
    show_id: int


class AdminShowFieldCb(CallbackData, prefix="adm_sf"):
    show_id: int
    field: str


class AdminCheckinCb(CallbackData, prefix="adm_ci"):
    show_id: int
    registration_id: int


class AdminManualCheckinCb(CallbackData, prefix="adm_mci"):
    show_id: int
    attendee_id: int


class AdminPartyCountCb(CallbackData, prefix="adm_pc"):
    show_id: int
    kind: str
    item_id: int
    count: int


class AdminTeamActionCb(CallbackData, prefix="adm_t"):
    action: str
    team_id: int


class AdminTeamFieldCb(CallbackData, prefix="adm_tf"):
    team_id: int
    field: str


class AdminVenueActionCb(CallbackData, prefix="adm_v"):
    action: str
    venue_id: int


class AdminVenueFieldCb(CallbackData, prefix="adm_vf"):
    venue_id: int
    field: str


class AdminAdChannelCb(CallbackData, prefix="adm_ch"):
    action: str
    channel_id: int


class AdminRevokeCb(CallbackData, prefix="admin_revoke"):
    telegram_id: int


class AdminFilterStatusCb(CallbackData, prefix="admin_filter_status"):
    status: str


class OnboardingCb(CallbackData, prefix="onboarding"):
    step: int


class TimePresetCb(CallbackData, prefix="time_preset", sep="|"):
    time: str  # "HH:MM"


class CityCb(CallbackData, prefix="city"):
    value: str


class VenueCb(CallbackData, prefix="venue"):
    venue_id: int  # 0 = custom


class TeamCb(CallbackData, prefix="team"):
    team_id: int  # 0 = other (manual input)
