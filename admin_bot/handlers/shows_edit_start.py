from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _make_calendar
from admin_bot.handlers.shows_edit_finish import _ask_edit_registrar

@router.callback_query(AdminShowActionCb.filter(F.action == "edit"))
async def start_edit(
    callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    await state.update_data(editing_show_id=show_id, current_show_id=show_id, reply_context="flow")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("✏️ Режим редактирования", reply_markup=flow_context_kb())
    if await crud.has_any_announcement_been_sent(session, show_id):
        await state.set_state(EditShowFSM.field)
        await callback.message.answer(
            "✏️ <b>Редактирование опубликованного шоу</b>\n\n"
            "При обычном обновлении записанные зрители получат сообщение, а в канале появится обновление. "
            "Для небольшой правки без рассылки выбери скрытое обновление.",
            reply_markup=edit_notification_mode_kb(show_id),
        )
    else:
        await state.set_state(EditShowFSM.field)
        await state.update_data(edit_notify=False)
        await callback.message.answer("Выбери поле для редактирования:", reply_markup=edit_show_fields_kb(show))


@router.callback_query(AdminShowActionCb.filter(F.action.in_({"edit_notify", "edit_silent"})))
async def choose_edit_notification_mode(
    callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    notify = callback_data.action == "edit_notify"
    await callback.answer("Обновление с уведомлениями" if notify else "Скрытое обновление")
    await state.set_state(EditShowFSM.field)
    await state.update_data(editing_show_id=show.id, edit_notify=notify)
    await callback.message.edit_text(
        "Выбери поле для редактирования:\n\n" +
        ("🔔 Изменения важных данных будут отправлены зрителям и в канал."
         if notify else "🤫 Изменения будут сохранены без сообщений зрителям и в канал."),
        reply_markup=edit_show_fields_kb(show),
    )


@router.callback_query(AdminShowFieldCb.filter())
async def choose_edit_field(
    callback: CallbackQuery, callback_data: AdminShowFieldCb, state: FSMContext,
    session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show_id = callback_data.show_id
    field = callback_data.field
    if field.startswith("group_"):
        show = await manageable_show(session, show_id, db_user, is_super_admin)
        if show is None:
            await deny(callback, "⛔ Нет доступа к этому шоу.")
            return
        group = field.removeprefix("group_")
        titles = {
            "main": "Выбери раздел для редактирования:", "basic": "🎭 Основные данные:",
            "venue": "📍 Место и вместимость:", "poster": "📝 Афиша:",
            "registration": "👥 Настройки записи:", "extra": "⚙️ Дополнительно:",
        }
        if group not in titles:
            await deny(callback, "Недоступный раздел.")
            return
        await callback.answer()
        await callback.message.edit_text(titles[group], reply_markup=edit_show_fields_kb(show, group))
        return
    allowed_fields = {
        "title", "team_name", "show_date", "city", "location", "location_url",
        "max_seats", "registrar_id", "poster_text", "poster_file_id",
        "checkin_enabled", "feedback_enabled",
    }
    show = await manageable_show(session, show_id, db_user, is_super_admin)
    if show is None or field not in allowed_fields:
        await deny(callback, "⛔ Недоступное поле или недостаточно прав.")
        return
    if field in {"checkin_enabled", "feedback_enabled"}:
        updated = await crud.update_show(session, show_id, **{field: not bool(getattr(show, field))})
        label = "Режим входа" if field == "checkin_enabled" else "Отзывы"
        enabled = bool(getattr(updated, field))
        await callback.answer(f"{label}: {'вкл' if enabled else 'выкл'}")
        await state.set_state(EditShowFSM.field)
        await callback.message.edit_text(
            "Выбери поле для редактирования:",
            reply_markup=edit_show_fields_kb(updated),
        )
        return
    if field == "show_date":
        await callback.answer()
        await state.set_state(EditShowFSM.show_date)
        await state.update_data(editing_show_id=show_id, editing_field=field)
        current = format_local(show.show_date)
        local_current = local_date(show.show_date)
        await callback.message.edit_text(
            f"Выбери новую дату шоу:\n\n<b>Текущее значение:</b>\n<code>{h(current)}</code>",
            reply_markup=await (await _make_calendar(session)).start_calendar(
                year=local_current.year, month=local_current.month,
            ),
        )
        return
    if field == "team_name":
        await callback.answer()
        await state.set_state(EditShowFSM.new_value)
        await state.update_data(editing_show_id=show_id, editing_field=field)
        await callback.message.edit_text(
            f"Выбери команду:\n\n<b>Текущее значение:</b> {h(show.team_name)}",
            reply_markup=team_select_kb(
                await crud.list_teams(session),
                back_callback=AdminShowFieldCb(show_id=show_id, field="group_basic").pack(),
                back_text="◀️ К основным данным",
            ),
        )
        return
    if field == "city":
        await callback.answer()
        await state.set_state(EditShowFSM.new_value)
        await state.update_data(editing_show_id=show_id, editing_field=field)
        await callback.message.edit_text(
            f"Выбери город:\n\n<b>Текущее значение:</b> {h(show.city)}", reply_markup=city_kb(),
        )
        return
    if field == "location":
        await callback.answer()
        await state.set_state(EditShowFSM.new_value)
        await state.update_data(editing_show_id=show_id, editing_field=field)
        await callback.message.edit_text(
            f"Выбери площадку:\n\n<b>Текущее значение:</b> {h(show.location)}",
            reply_markup=venue_kb(await crud.list_venues(session)),
        )
        return
    await callback.answer()
    await state.set_state(EditShowFSM.new_value)
    await state.update_data(editing_show_id=show_id, editing_field=field)

    prompts = {
        "title": "Введи новое название шоу:",
        "team_name": "Введи новое название команды:",
        "show_date": "Введи новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ):",
        "city": "Введи новый город:",
        "location": "Введи новое название площадки:",
        "location_url": "Введи ссылку на Google Maps (или /skip чтобы убрать):",
        "max_seats": "Введи новое количество мест:",
        "registrar_id": "Выбери ответственного за записи:",
        "poster_text": "Введи новый текст афиши (или /skip чтобы очистить):",
        "poster_file_id": "Отправь новое изображение афиши:",
    }

    current_values = {
        "title": show.title,
        "team_name": show.team_name,
        "show_date": format_local(show.show_date),
        "city": show.city,
        "location": show.location,
        "location_url": show.location_url or "(не указана)",
        "max_seats": str(show.max_seats),
        "registrar_id": _registrar_name(show.registrar, show.registrar_username) if show else "(не указан)",
        "poster_text": show.poster_text or "(не указан)",
    } if show else {}

    prompt = prompts.get(field, "Введи новое значение:")
    current = current_values.get(field)

    if field == "registrar_id":
        await _ask_edit_registrar(callback.message, state)
        return

    if current and field != "poster_file_id":
        text = f"{prompt}\n\n<b>Текущее значение:</b>\n<code>{h(current)}</code>"
    else:
        text = prompt

    await callback.message.edit_text(text)
