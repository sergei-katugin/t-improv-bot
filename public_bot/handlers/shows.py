from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

from sqlalchemy.ext.asyncio import AsyncSession

from db import crud
from db.models import User
from public_bot.keyboards.inline import shows_list_kb, show_detail_kb
from public_bot.callbacks import ShowCb
from public_bot.show_utils import NO_LINK_PREVIEW, show_text
from html_utils import h

router = Router()


class FilterFSM(StatesGroup):
    enter_city = State()
    enter_venue = State()



@router.message(Command("shows"))
@router.message(F.text.in_({"🎭 Все шоу", "🎭 Шоу"}))
@router.callback_query(F.data == "pub_shows_list")
async def cmd_shows(event, state: FSMContext, db_user: User, session: AsyncSession):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()

    shows = await crud.list_upcoming_shows(session)
    my_regs = await crud.get_user_registrations(session, db_user.id)

    registered_ids = {r.show_id for r in my_regs}

    if not shows:
        text = "😔 Сейчас нет предстоящих шоу. Загляни позже!"
        if isinstance(event, Message):
            await msg.answer(text)
        elif msg.photo:
            await msg.answer(text)
        else:
            await msg.edit_text(text)
        return

    text = "🎭 <b>Предстоящие шоу</b>\nВыбери интересующее:"
    kb = shows_list_kb(shows, registered_ids)
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=kb)
    elif msg.photo:
        await msg.answer(text, reply_markup=kb)
    else:
        await msg.edit_text(text, reply_markup=kb)



@router.callback_query(ShowCb.filter())
async def show_detail(callback: CallbackQuery, callback_data: ShowCb, db_user: User, session: AsyncSession):
    show_id = callback_data.show_id
    await callback.answer()

    show = await crud.get_show(session, show_id)
    if show is None:
        await callback.message.edit_text("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    reg = await crud.get_registration(session, show_id, db_user.id)

    seats_left = max(0, show.max_seats - active_count)
    is_registered = reg is not None and not reg.is_cancelled
    text = show_text(show, seats_left, reg=reg)
    kb = show_detail_kb(show, is_registered, seats_left)

    if callback.message.photo:
        await callback.message.answer(
            text,
            reply_markup=kb,
            link_preview_options=NO_LINK_PREVIEW,
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=kb,
            link_preview_options=NO_LINK_PREVIEW,
        )


# ── Filters ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "pub_filter_city")
async def filter_city_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FilterFSM.enter_city)
    try:
        await callback.message.edit_text("Введи название города:")
    except TelegramBadRequest:
        await callback.message.answer("Введи название города:")


@router.message(FilterFSM.enter_city, F.text)
async def filter_by_city(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    city = message.text.strip()
    await state.clear()

    shows = await crud.list_upcoming_shows(session, city=city)
    my_regs = await crud.get_user_registrations(session, db_user.id)

    registered_ids = {r.show_id for r in my_regs}

    if not shows:
        await message.answer(f"Нет шоу в городе «{h(city)}».", reply_markup=shows_list_kb([], registered_ids))
        return

    await message.answer(
        f"🎭 Шоу в городе <b>{h(city)}</b>:",
        reply_markup=shows_list_kb(shows, registered_ids),
    )


@router.callback_query(F.data == "pub_filter_venue")
async def filter_venue_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(FilterFSM.enter_venue)
    try:
        await callback.message.edit_text("Введи название площадки:")
    except TelegramBadRequest:
        await callback.message.answer("Введи название площадки:")


@router.message(FilterFSM.enter_venue, F.text)
async def filter_by_venue(message: Message, state: FSMContext, db_user: User, session: AsyncSession):
    venue = message.text.strip()
    await state.clear()

    shows = await crud.list_upcoming_shows(session, location=venue)
    my_regs = await crud.get_user_registrations(session, db_user.id)

    registered_ids = {r.show_id for r in my_regs}

    if not shows:
        await message.answer(f"Нет шоу на площадке «{h(venue)}».")
        return

    await message.answer(
        f"🎭 Шоу на площадке <b>{h(venue)}</b>:",
        reply_markup=shows_list_kb(shows, registered_ids),
    )


@router.callback_query(F.data == "pub_no_seats")
async def no_seats(callback: CallbackQuery):
    await callback.answer("К сожалению, мест больше нет 😔", show_alert=True)
