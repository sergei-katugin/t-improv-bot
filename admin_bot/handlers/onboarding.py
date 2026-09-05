from app_logging import get_project_logger
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from admin_bot.callbacks import OnboardingCb
from admin_bot.keyboards.reply import main_menu_kb, miniapp_launch_kb
from db import crud

router = Router()

_STEPS = {
    1: (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Основное управление шоу находится в Mini App: там создаются афиши, публикации и настройки.\n\n"
        "<i>1 / 3</i>"
    ),
    2: (
        "⚡ <b>Что осталось в боте</b>\n\n"
        "Быстрый просмотр афиш и записей, добавление зрителя вручную и подключение рабочего чата.\n\n"
        "<i>2 / 3</i>"
    ),
    3: (
        "🔔 <b>Напоминания</b>\n\n"
        "Автоматические напоминания продолжат работать. Дополнительное управление ими доступно в Mini App.\n\n"
        "<i>3 / 3</i>"
    ),
}

_LAST_STEP = max(_STEPS)


def _kb(step: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if step < _LAST_STEP:
        builder.button(text="Дальше →", callback_data=OnboardingCb(step=step + 1).pack())
    else:
        builder.button(text="Поехали! 🚀", callback_data=OnboardingCb(step=0).pack())
    return builder.as_markup()


async def start_onboarding(message: Message) -> None:
    await message.answer(_STEPS[1], reply_markup=_kb(1))


@router.message(F.text == "ℹ️ Инфо")
@router.message(Command("info", "help"))
async def cmd_info(message: Message):
    await start_onboarding(message)


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    await message.answer(
        "🔐 <b>Конфиденциальность</b>\n\n"
        "Бот хранит Telegram ID, имя и username организатора, созданные шоу и команды, "
        "чтобы управлять доступом и сохранять историю мероприятий. Данные доступны только уполномоченным организаторам и администраторам.\n\n"
        "Полное описание доступно в публичном боте командой /privacy. Удаление персональных данных — /delete_me в публичном боте; "
        "созданные шоу и команды при этом сохраняются с обезличенным автором."
    )


@router.callback_query(F.data == "settings_info")
async def settings_info_cb(callback: CallbackQuery):
    await callback.answer()
    await start_onboarding(callback.message)


@router.callback_query(OnboardingCb.filter())
async def onboarding_cb(
    callback: CallbackQuery,
    callback_data: OnboardingCb,
    session: AsyncSession,
    is_super_admin: bool = False,
):
    await callback.answer()
    step = callback_data.step

    if step == 0:
        await crud.mark_onboarding_done(session, callback.from_user.id)
        get_project_logger(__name__).info("onboarding completed for user=%s", callback.from_user.id)
        await callback.message.edit_text(
            "✅ Готово! Создание и управление афишами доступно в Mini App.",
            reply_markup=miniapp_launch_kb(),
        )
        await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text(_STEPS[step], reply_markup=_kb(step))
