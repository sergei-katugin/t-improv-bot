from aiogram.filters.callback_data import CallbackData


class ShowCb(CallbackData, prefix="pub_show"):
    show_id: int


class RegisterCb(CallbackData, prefix="pub_register"):
    show_id: int


class ConfirmRegCb(CallbackData, prefix="pub_confirm_reg"):
    show_id: int


class CancelRegCb(CallbackData, prefix="pub_cancel"):
    show_id: int


class EditGuestsCb(CallbackData, prefix="pub_edit_guests"):
    show_id: int


class GuestsCb(CallbackData, prefix="guests"):
    show_id: int
    guests: int


class GuestsCustomCb(CallbackData, prefix="guests_custom"):
    show_id: int


class RemindToggleCb(CallbackData, prefix="remind_toggle"):
    show_id: int
    field: str
    value: int
