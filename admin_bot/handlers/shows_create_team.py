from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _make_calendar

@router.callback_query(CreateShowFSM.team_name, F.data == "team_show_existing")
async def team_show_existing(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    teams = await crud.list_teams(session)
    if not teams:
        await callback.answer("Нет сохранённых команд. Создай новую или введи вручную.", show_alert=True)
        return
    await callback.message.edit_text(
        f"{_progress(1)}Выбери команду из списка:",
        reply_markup=team_select_kb(teams),
    )


@router.callback_query(CreateShowFSM.team_name, F.data == "team_back_to_entry")
async def team_back_to_entry(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"{_progress(1)}Выбери команду из списка или введи своё название:",
        reply_markup=team_kb(),
    )


@router.callback_query(CreateShowFSM.team_name, TeamCb.filter())
async def process_team_select(callback: CallbackQuery, callback_data: TeamCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    if callback_data.team_id == 0:
        # "Другая" — manual text input
        await callback.message.edit_text(
            f"{_progress(1)}Введи название команды:",
            reply_markup=fsm_cancel_kb(),
        )
        await state.update_data(team_id=None, _team_manual=True)
        return
    team = await crud.get_team(session, callback_data.team_id)
    if team is None:
        await callback.message.answer("Команда не найдена. Попробуй ещё раз.")
        return
    await state.update_data(team_name=team.name, team_id=team.id, _team_manual=False)
    await callback.message.edit_text(f"✅ Команда: {h(team.name)}")
    await callback.message.answer(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())
    await state.set_state(CreateShowFSM.title)


@router.message(CreateShowFSM.team_name, F.text)
async def process_team_name_manual(message: Message, state: FSMContext, session: AsyncSession):
    """Manual text input for 'Другая' team."""
    data = await state.get_data()
    if not data.get("_team_manual"):
        # Guard: if user typed without clicking "Другая", show the keyboard
        teams = await crud.list_teams(session)
        await message.answer(f"{_progress(1)}Выбери команду:", reply_markup=team_select_kb(teams))
        return
    if len(message.text.strip()) < 2:
        await message.answer("Название команды слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(team_name=message.text.strip(), team_id=None, _team_manual=False)
    await state.set_state(CreateShowFSM.title)
    await message.answer(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())


@router.message(CreateShowFSM.title, F.text)
async def process_title(message: Message, state: FSMContext, session: AsyncSession):
    if len(message.text.strip()) < 2:
        await message.answer("Название шоу слишком короткое. Попробуй ещё раз:", reply_markup=fsm_cancel_kb())
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateShowFSM.show_date)
    now = local_now()
    await message.answer(
        f"{_progress(3)}Выбери дату шоу:",
        reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
    )


@router.message(CreateShowFSM.show_date)
async def show_date_text_guard(message: Message, state: FSMContext, session: AsyncSession):
    now = local_now()
    await message.answer(
        "👆 Выбери дату кнопками выше.",
        reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
    )


@router.callback_query(CreateShowFSM.show_date, simple_cal_callback.filter())
async def process_calendar(callback: CallbackQuery, callback_data: dict, state: FSMContext, session: AsyncSession):
    selected, date = await (await _make_calendar(session)).process_selection(callback, callback_data)
    if not selected:
        return
    if date.date() < local_now().date():
        await callback.answer("❌ Дата в прошлом, выбери другую.", show_alert=True)
        return
    await state.update_data(picked_date=date.strftime("%d.%m.%Y"))
    await state.set_state(CreateShowFSM.select_time)
    await callback.message.answer(
        f"✅ Дата: {date.strftime('%d.%m.%Y')}\n\n"
        f"{_progress(3)}Выбери время начала:",
        reply_markup=_time_kb(),
    )


def _time_kb():
    from aiogram.utils.keyboard import InlineKeyboardBuilder as IKB
    slots = ["17:30", "18:00", "18:30", "19:00", "19:30", "20:00", "20:30"]
    builder = IKB()
    for t in slots:
        builder.button(text=t, callback_data=TimePresetCb(time=t).pack())
    builder.button(text="✏️ Другое", callback_data="time_custom")
    builder.button(text="◀️ Назад",  callback_data="fsm_back")
    builder.button(text="❌ Отмена", callback_data="fsm_cancel")
    builder.adjust(4, 3, 2)
    return builder.as_markup()


@router.callback_query(CreateShowFSM.select_time, TimePresetCb.filter())
async def process_time_preset(callback: CallbackQuery, callback_data: TimePresetCb, state: FSMContext, session: AsyncSession):
    await callback.answer()
    await _save_time(callback_data.time, callback.message, state, session, edit=True)


@router.callback_query(CreateShowFSM.select_time, F.data == "time_custom")
async def process_time_custom(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        f"{_progress(3)}Введи время начала (ЧЧ:ММ), например 19:00:",
        reply_markup=fsm_cancel_kb(),
    )


@router.message(CreateShowFSM.select_time, F.text)
async def process_time(message: Message, state: FSMContext, session: AsyncSession):
    raw = message.text.strip()
    try:
        datetime.strptime(raw, "%H:%M")
    except ValueError:
        await message.answer("Неверный формат. Введи время как ЧЧ:ММ, например 19:00:", reply_markup=fsm_cancel_kb())
        return
    await _save_time(raw, message, state, session, edit=False)


async def _save_time(raw: str, msg, state: FSMContext, session: AsyncSession, edit: bool):
    data = await state.get_data()
    local_dt = datetime.strptime(f"{data['picked_date']} {raw}", "%d.%m.%Y %H:%M")
    if local_dt.replace(tzinfo=local_now().tzinfo) <= local_now():
        text = "❌ Дата и время уже в прошлом. Выбери другое время:"
        if edit:
            await msg.edit_text(text, reply_markup=_time_kb())
        else:
            await msg.answer(text, reply_markup=_time_kb())
        return
    await state.update_data(show_date=local_naive_to_utc(local_dt), show_date_str=f"{data['picked_date']} {raw}")
    await state.set_state(CreateShowFSM.select_venue)
    venues = await crud.list_venues(session)
    confirm_text = f"✅ Время: {raw}"
    if edit:
        await msg.edit_text(confirm_text)
    else:
        await msg.answer(confirm_text)
    await msg.answer(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))
