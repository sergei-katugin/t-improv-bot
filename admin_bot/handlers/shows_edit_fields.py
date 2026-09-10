from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _make_calendar
from admin_bot.handlers.shows_create_team import _time_kb
from admin_bot.handlers.shows_edit_finish import _apply_edit

@router.callback_query(EditShowFSM.new_value, TeamCb.filter())
async def edit_team_select(
    callback: CallbackQuery, callback_data: TeamCb, state: FSMContext, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    if data.get("editing_field") != "team_name":
        return
    await callback.answer()
    if callback_data.team_id == 0:
        await callback.message.edit_text("Введи название команды:", reply_markup=fsm_cancel_kb())
        return
    team = await crud.get_team(session, callback_data.team_id)
    if team is None:
        await callback.message.answer("Команда не найдена.")
        return
    await _apply_edit(callback.message, state, session, team.name, db_user=db_user, is_super_admin=is_super_admin)


@router.callback_query(EditShowFSM.new_value, CityCb.filter())
async def edit_city_select(
    callback: CallbackQuery, callback_data: CityCb, state: FSMContext, session: AsyncSession,
    bot: Bot, public_bot: Bot, db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    if data.get("editing_field") != "city":
        return
    await callback.answer()
    if callback_data.value == "custom":
        await callback.message.edit_text("Введи название города:", reply_markup=fsm_cancel_kb())
        return
    await _apply_edit(callback.message, state, session, callback_data.value, bot=bot, public_bot=public_bot, db_user=db_user, is_super_admin=is_super_admin)


@router.callback_query(EditShowFSM.new_value, VenueCb.filter())
async def edit_venue_select(
    callback: CallbackQuery, callback_data: VenueCb, state: FSMContext, session: AsyncSession,
    bot: Bot, public_bot: Bot, db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    if data.get("editing_field") != "location":
        return
    await callback.answer()
    if callback_data.venue_id == 0:
        await callback.message.edit_text("Введи название площадки/театра:", reply_markup=fsm_cancel_kb())
        return
    venue = await crud.get_venue(session, callback_data.venue_id)
    if venue is None:
        await callback.message.answer("Площадка не найдена.")
        return
    await _apply_edit(
        callback.message, state, session,
        {"location": venue.name, "location_url": venue.maps_url, "city": venue.city, "max_seats": venue.default_seats},
        bot=bot, public_bot=public_bot, db_user=db_user, is_super_admin=is_super_admin,
    )


@router.message(EditShowFSM.show_date)
async def edit_date_text_guard(message: Message, session: AsyncSession):
    now = local_now()
    await message.answer(
        "👆 Выбери дату кнопками выше.",
        reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
    )


@router.callback_query(EditShowFSM.show_date, simple_cal_callback.filter())
async def process_edit_calendar(callback: CallbackQuery, callback_data: dict, state: FSMContext, session: AsyncSession):
    selected, selected_date = await (await _make_calendar(session)).process_selection(callback, callback_data)
    if not selected:
        return
    if selected_date.date() < local_now().date():
        await callback.answer("❌ Дата в прошлом, выбери другую.", show_alert=True)
        return
    await state.update_data(picked_date=selected_date.strftime("%d.%m.%Y"))
    await state.set_state(EditShowFSM.select_time)
    await callback.message.answer(
        f"✅ Дата: {selected_date.strftime('%d.%m.%Y')}\n\nВыбери время начала:",
        reply_markup=_time_kb(),
    )


@router.callback_query(EditShowFSM.select_time, TimePresetCb.filter())
async def process_edit_time_preset(
    callback: CallbackQuery, callback_data: TimePresetCb, state: FSMContext,
    session: AsyncSession, bot: Bot, public_bot: Bot, db_user=None, is_super_admin: bool = False,
):
    await callback.answer()
    await _save_edit_datetime(callback_data.time, callback.message, state, session, bot, public_bot, db_user, is_super_admin)


@router.callback_query(EditShowFSM.select_time, F.data == "time_custom")
async def process_edit_time_custom(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Введи время начала (ЧЧ:ММ), например 19:00:", reply_markup=fsm_cancel_kb())


@router.message(EditShowFSM.select_time, F.text)
async def process_edit_time(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot, public_bot: Bot,
    db_user=None, is_super_admin: bool = False,
):
    await _save_edit_datetime(message.text.strip(), message, state, session, bot, public_bot, db_user, is_super_admin)


async def _save_edit_datetime(raw, message, state, session, bot, public_bot, db_user, is_super_admin):
    data = await state.get_data()
    try:
        local_value = datetime.strptime(f"{data['picked_date']} {raw}", "%d.%m.%Y %H:%M")
    except (ValueError, KeyError):
        await message.answer("Неверное время. Введи как ЧЧ:ММ, например 19:00:")
        return
    if local_value.replace(tzinfo=local_now().tzinfo) <= local_now():
        await message.answer("❌ Дата и время уже в прошлом. Выбери другое время:", reply_markup=_time_kb())
        return
    await _apply_edit(
        message, state, session, local_naive_to_utc(local_value), bot=bot, public_bot=public_bot,
        db_user=db_user, is_super_admin=is_super_admin,
    )
