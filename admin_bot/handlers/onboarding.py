from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from admin_bot.callbacks import OnboardingCb
from admin_bot.keyboards.reply import main_menu_kb
from db import crud

router = Router()

_STEPS = {
    1: (
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Этот бот помогает управлять импровизационными шоу: "
        "создавать события, принимать записи зрителей и публиковать анонсы.\n\n"
        "<i>1 / 5</i>"
    ),
    2: (
        "📢 <b>Анонсы в канале</b>\n\n"
        "Когда шоу создано, ты сам выбираешь когда опубликовать анонс "
        "в специальный Telegram-канал. Зрители увидят дату и место, "
        "а кнопка «Записаться» откроет бота — регистрация проходит прямо в нём.\n\n"
        "<i>2 / 5</i>"
    ),
    3: (
        "🔔 <b>Напоминания</b>\n\n"
        "Бот автоматически напомнит каждому записавшемуся о шоу. "
        "Также можно отправить напоминание вручную в любой момент — "
        "например, если добавилась важная информация.\n\n"
        "<i>3 / 5</i>"
    ),
    4: (
        "✏️ <b>Редактирование и отмена</b>\n\n"
        "Любое шоу можно отредактировать после создания — изменить дату, место, текст афиши и другие поля. "
        "Если шоу отменяется, бот автоматически уведомит всех записавшихся зрителей.\n\n"
        "<i>4 / 5</i>"
    ),
    5: (
        "👥 <b>Список зрителей</b>\n\n"
        "В карточке каждого шоу можно посмотреть кто записался, сколько мест осталось "
        "и добавить или удалить зрителя вручную — удобно для брони по телефону или личной просьбе.\n\n"
        "<i>5 / 5</i>"
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
@router.message(Command("info"))
async def cmd_info(message: Message):
    await start_onboarding(message)


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
        next_kb = InlineKeyboardBuilder()
        next_kb.button(text="🆕 Создать шоу",     callback_data="admin_create_show")
        next_kb.button(text="👥 Создать команду", callback_data="admin_team_add_from_onboarding")
        next_kb.button(text="📋 Афиша",           callback_data="admin_shows_list")
        next_kb.adjust(1)
        await callback.message.edit_text(
            "✅ Готово! С чего начнём?",
            reply_markup=next_kb.as_markup(),
        )
        await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text(_STEPS[step], reply_markup=_kb(step))
