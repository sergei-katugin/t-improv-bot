from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _make_calendar
from admin_bot.handlers.shows_create_team import _time_kb
from admin_bot.handlers.shows_listing import show_detail

@router.callback_query(AdminShowActionCb.filter(F.action == "clone"))
async def clone_show_start(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await state.set_state(CloneShowFSM.show_date)
    await state.update_data(clone_show_id=show.id)
    await callback.message.edit_text(
        f"📄 Создаём новое шоу по шаблону «{h(show.title)}».\n\nВыбери новую дату:",
        reply_markup=await (await _make_calendar(session)).start_calendar(
            year=local_now().year, month=local_now().month,
        ),
    )


@router.callback_query(CloneShowFSM.show_date, simple_cal_callback.filter())
async def clone_show_date(callback: CallbackQuery, callback_data: dict, state: FSMContext, session: AsyncSession):
    selected, selected_date = await (await _make_calendar(session)).process_selection(callback, callback_data)
    if not selected:
        return
    if selected_date.date() < local_now().date():
        await callback.answer("❌ Дата в прошлом.", show_alert=True)
        return
    await state.update_data(clone_date=selected_date.strftime("%d.%m.%Y"))
    await state.set_state(CloneShowFSM.select_time)
    await callback.message.answer("Выбери время начала:", reply_markup=_time_kb())


@router.callback_query(CloneShowFSM.select_time, TimePresetCb.filter())
async def clone_show_time_preset(callback: CallbackQuery, callback_data: TimePresetCb, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    await callback.answer()
    await _finish_clone_show(callback.message, callback_data.time, state, session, db_user, is_super_admin)


@router.callback_query(CloneShowFSM.select_time, F.data == "time_custom")
async def clone_show_custom_time(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("Введи время начала (ЧЧ:ММ), например 19:00:", reply_markup=fsm_cancel_kb())


@router.message(CloneShowFSM.select_time, F.text)
async def clone_show_time_text(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    await _finish_clone_show(message, message.text.strip(), state, session, db_user, is_super_admin)


async def _finish_clone_show(message: Message, raw_time: str, state: FSMContext, session: AsyncSession, db_user, is_super_admin: bool) -> None:
    data = await state.get_data()
    try:
        local_value = datetime.strptime(f"{data['clone_date']} {raw_time}", "%d.%m.%Y %H:%M")
    except (ValueError, KeyError):
        await message.answer("Неверное время. Введи как ЧЧ:ММ, например 19:00:")
        return
    if local_value.replace(tzinfo=local_now().tzinfo) <= local_now():
        await message.answer("Дата и время должны быть в будущем.")
        return
    source = await manageable_show(session, data.get("clone_show_id"), db_user, is_super_admin)
    if source is None:
        await state.clear()
        await message.answer("⛔ Исходное шоу недоступно.")
        return
    clone = await crud.create_show(
        session, title=source.title, team_name=source.team_name,
        show_date=local_naive_to_utc(local_value), location=source.location,
        location_url=source.location_url, city=source.city,
        poster_text=source.poster_text, poster_file_id=source.poster_file_id,
        max_seats=source.max_seats, creator_id=db_user.id,
        max_guests=source.max_guests,
        registrar_id=source.registrar_id, registrar_username=source.registrar_username,
        checkin_enabled=source.checkin_enabled, feedback_enabled=source.feedback_enabled,
    )
    await state.clear()
    await state.update_data(reply_context="show", current_show_id=clone.id)
    await message.answer(
        f"✅ Создано новое шоу «{h(clone.title)}» на {format_local(clone.show_date)}.\n"
        "Записи, публикации и рабочий канал не копировались.",
        reply_markup=show_created_kb(clone.id),
    )


@router.callback_query(AdminShowActionCb.filter(F.action == "toggle_checkin"))
async def toggle_show_checkin(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    session: AsyncSession,
    state: FSMContext,
    db_user=None,
    is_super_admin: bool = False,
):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    show = await crud.update_show(session, show.id, checkin_enabled=not show.checkin_enabled)
    await callback.answer(f"Режим входа {'включён' if show.checkin_enabled else 'выключен'}")
    await show_detail(callback, AdminShowActionCb(action="open", show_id=show.id), session, state, answer_callback=False)


@router.callback_query(AdminShowActionCb.filter(F.action == "toggle_feedback"))
async def toggle_show_feedback(
    callback: CallbackQuery,
    callback_data: AdminShowActionCb,
    session: AsyncSession,
    state: FSMContext,
    db_user=None,
    is_super_admin: bool = False,
):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    show = await crud.update_show(session, show.id, feedback_enabled=not show.feedback_enabled)
    await callback.answer(f"Отзывы {'включены' if show.feedback_enabled else 'выключены'}")
    await show_detail(callback, AdminShowActionCb(action="open", show_id=show.id), session, state, answer_callback=False)
