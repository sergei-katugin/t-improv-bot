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
        "👋 <b>Привет! Это панель организатора T·IMPRO</b>\n\n"
        "Здесь можно создавать афиши, собирать записи и следить за заполняемостью.\n\n"
        "Основная работа идёт в <b>Mini App</b> — оно открывается прямо в Telegram.\n\n"
        "<i>1 / 4</i>"
    ),
    2: (
        "🎭 <b>Создай первую афишу</b>\n\n"
        "1. Открой Mini App.\n"
        "2. Нажми <b>«Создать афишу»</b>.\n"
        "3. Выбери команду, площадку, дату и число мест.\n"
        "4. Проверь превью и опубликуй анонс.\n\n"
        "Черновик можно вернуться и дополнить позже.\n\n"
        "<i>2 / 4</i>"
    ),
    3: (
        "🔔 <b>Подключи чат записей</b>\n\n"
        "Добавь этого админ-бота в рабочую группу или канал. Бот сам напишет, что чат подключён.\n\n"
        "Затем выбери этот чат в афише. Туда будут приходить новые записи и текущая заполняемость.\n\n"
        "<i>3 / 4</i>"
    ),
    4: (
        "✅ <b>Всё готово</b>\n\n"
        "• Зрители записываются через публичного бота.\n"
        "• Запись из Instagram, звонка или личного сообщения можно добавить кнопкой прямо в чате записей.\n"
        "• Напоминания и сбор отзывов работают автоматически.\n\n"
        "<i>4 / 4</i>"
    ),
}

_LAST_STEP = max(_STEPS)


def _kb(step: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if step < _LAST_STEP:
        builder.button(text="Дальше →", callback_data=OnboardingCb(step=step + 1).pack())
    else:
        builder.button(text="Готово →", callback_data=OnboardingCb(step=0).pack())
    if step > 1:
        builder.button(text="← Назад", callback_data=OnboardingCb(step=step - 1).pack())
    if step < _LAST_STEP:
        builder.button(text="Пропустить", callback_data=OnboardingCb(step=0).pack())
    builder.adjust(1)
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
            "✅ <b>Готово!</b> Открой Mini App и создай первую афишу.",
            reply_markup=miniapp_launch_kb(),
        )
        await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text(_STEPS[step], reply_markup=_kb(step))
