from aiogram.filters.callback_data import CallbackData


class AdminShowCb(CallbackData, prefix="admin_show"):
    show_id: int


class AdminRegsCb(CallbackData, prefix="admin_regs"):
    show_id: int


class AdminAddManualCb(CallbackData, prefix="admin_add_manual"):
    show_id: int


class AdminDelManualStartCb(CallbackData, prefix="admin_del_manual_start"):
    show_id: int


class AdminPreviewCb(CallbackData, prefix="admin_preview"):
    show_id: int


class AdminQrCb(CallbackData, prefix="admin_qr"):
    show_id: int


class AdminShowLinkCb(CallbackData, prefix="admin_show_link"):
    show_id: int


class AdminEditCb(CallbackData, prefix="admin_edit"):
    show_id: int


class AdminAnnounceCb(CallbackData, prefix="admin_announce"):
    show_id: int


class AdminRemindCb(CallbackData, prefix="admin_remind"):
    show_id: int


class AdminCancelShowCb(CallbackData, prefix="admin_cancel_show"):
    show_id: int


class AdminConfirmCancelCb(CallbackData, prefix="admin_confirm_cancel"):
    show_id: int


class AdminRestoreShowCb(CallbackData, prefix="admin_restore_show"):
    show_id: int


class AdminEditFieldCb(CallbackData, prefix="admin_edit_field"):
    show_id: int
    field: str


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


class AdminTeamCb(CallbackData, prefix="admin_team"):
    team_id: int


class AdminTeamFieldCb(CallbackData, prefix="admin_team_field"):
    team_id: int
    field: str


class AdminVenueCb(CallbackData, prefix="admin_venue"):
    venue_id: int


class AdminVenueFieldCb(CallbackData, prefix="admin_venue_field"):
    venue_id: int
    field: str


class AdminVenueConfirmDeleteCb(CallbackData, prefix="admin_venue_del"):
    venue_id: int


class AdminTeamConfirmDeleteCb(CallbackData, prefix="admin_team_del"):
    team_id: int
