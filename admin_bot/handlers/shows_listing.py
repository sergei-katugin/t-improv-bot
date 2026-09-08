from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()

async def _render_shows_list(msg, state: FSMContext, session: AsyncSession, edit: bool = False, can_manage: bool = True):
    data = await state.get_data()
    f_status = data.get("f_status", "active")
    f_team = data.get("f_team")
    f_year = data.get("f_year")
    page = max(0, int(data.get("shows_page", 0)))

    rows = await crud.list_all_shows(
        session,
        status=f_status,
        team=f_team,
        year=f_year,
        limit=_SHOWS_PAGE_SIZE + 1,
        offset=page * _SHOWS_PAGE_SIZE,
    )
    has_next = len(rows) > _SHOWS_PAGE_SIZE
    shows = rows[:_SHOWS_PAGE_SIZE]

    parts = [f"📋 <b>Все шоу</b>"]
    filters = []
    if f_status != "all":
        filters.append(_STATUS_LABELS[f_status])
    if f_team:
        filters.append(f_team)
    if f_year:
        filters.append(str(f_year))
    if filters:
        parts.append(f" · {', '.join(filters)}")
    parts.append(f" · стр. {page + 1}:" if shows else ":")
    text = "".join(parts) if shows else "Нет шоу по выбранному фильтру."

    kb = shows_list_kb(shows, can_manage=can_manage, page=page, has_next=has_next)
    try:
        if edit:
            await msg.edit_text(text, reply_markup=kb)
        else:
            await msg.answer(text, reply_markup=kb)
    except Exception:
        await msg.answer(text, reply_markup=kb)
    data = await state.get_data()
    if data.get("reply_context") != "shows":
        await state.update_data(reply_context="shows", current_show_id=None)
        await msg.answer("⌨️ Быстрые действия для списка шоу", reply_markup=shows_context_kb())


@router.callback_query(F.data == "admin_shows_list")
async def cmd_shows_callback(callback: CallbackQuery, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await callback.answer()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(callback.message, state, session, edit=True, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(F.data.startswith("admin_shows_page:"))
async def shows_page(callback: CallbackQuery, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    page = max(0, int(callback.data.rsplit(":", 1)[1]))
    await state.update_data(shows_page=page)
    await callback.answer()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(callback.message, state, session, edit=True, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(F.data == "admin_shows_filter")
async def shows_filter_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    current = {k: data.get(k) for k in ("status", "team", "year")
               if data.get(k) or k == "status"}
    current.setdefault("status", data.get("f_status", "all"))
    current["team"] = data.get("f_team")
    current["year"] = data.get("f_year")
    await callback.message.edit_text(
        "🔍 <b>Фильтр шоу</b>\n\nНажми чтобы переключить значение:",
        reply_markup=shows_filter_kb(current),
    )


@router.callback_query(AdminFilterStatusCb.filter())
async def filter_set_status(callback: CallbackQuery, callback_data: AdminFilterStatusCb, state: FSMContext):
    new_status = callback_data.status
    await state.update_data(f_status=new_status, shows_page=0)
    await callback.answer(f"Статус: {_STATUS_LABELS[new_status]}")
    data = await state.get_data()
    current = {"status": new_status, "team": data.get("f_team"), "year": data.get("f_year")}
    try:
        await callback.message.edit_reply_markup(reply_markup=shows_filter_kb(current))
    except Exception:
        pass


@router.callback_query(F.data == "admin_filter_reset")
async def filter_reset(callback: CallbackQuery, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.update_data(f_status="active", f_team=None, f_year=None, shows_page=0)
    await callback.answer("Фильтр сброшен")
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(callback.message, state, session, edit=True, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(F.data == "admin_filter_team")
async def filter_set_team(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(EditShowFSM.field)
    await state.update_data(_filter_mode="team")
    await callback.message.edit_text(
        "Введи название команды для фильтра (или /skip чтобы убрать):"
    )


@router.callback_query(F.data == "admin_filter_year")
async def filter_set_year(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(EditShowFSM.field)
    await state.update_data(_filter_mode="year")
    await callback.message.edit_text(
        "Введи год (например 2026), или /skip чтобы убрать фильтр по году:"
    )


@router.message(EditShowFSM.field, F.text)
async def filter_input(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    data = await state.get_data()
    mode = data.get("_filter_mode")
    if not mode:
        return
    raw = message.text.strip()
    if raw == "/skip":
        await state.update_data(**{f"f_{mode}": None, "_filter_mode": None, "shows_page": 0})
    elif mode == "year":
        try:
            year = int(raw)
            if not 2000 <= year <= 2100:
                raise ValueError
            await state.update_data(f_year=year, _filter_mode=None, shows_page=0)
        except ValueError:
            await message.answer("Введи корректный год (например 2026) или /skip:")
            return
    else:
        await state.update_data(f_team=raw, _filter_mode=None, shows_page=0)
    await state.set_state(None)
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(message, state, session, edit=False, can_manage=_can_manage(is_super_admin, db_user))


@router.callback_query(AdminShowActionCb.filter(F.action == "open"))
async def show_detail(
    callback: CallbackQuery, callback_data: AdminShowActionCb, session: AsyncSession,
    state: FSMContext, answer_callback: bool = True,
):
    show_id = callback_data.show_id
    show = await crud.get_show(session, show_id)
    if show is None:
        if answer_callback:
            await callback.answer("Шоу не найдено.", show_alert=True)
        await callback.message.edit_text("Шоу не найдено.")
        return
    active_count = await crud.count_active_registrations(session, show_id)
    tg_id = callback.from_user.id
    user = await crud.get_user_by_telegram_id(session, tg_id)

    if not (
        (show.creator and show.creator.telegram_id == tg_id)
        or tg_id in ADMIN_ID_LIST
        or (user and user.role == UserRole.admin)
    ):
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    if answer_callback:
        await callback.answer()

    is_creator = (show.creator and show.creator.telegram_id == tg_id) or tg_id in ADMIN_ID_LIST
    if user and user.role == UserRole.admin:
        is_creator = True

    seats_left = show.max_seats - active_count
    creator = show.creator
    creator_label = ""
    if creator:
        name = creator.first_name or creator.username or str(creator.telegram_id)
        uname = f" (@{h(creator.username)})" if creator.username else ""
        creator_label = f"👤 Создатель: {h(name)}{uname}\n"

    registrar = show.registrar
    registrar_label = ""
    if registrar or show.registrar_username:
        registrar_label = f"{_registrar_line(show)}\n"
    else:
        registrar_label = "👥 Ответственный за записи: (через бот)\n"
    registration_chat_label = (
        f"🔔 Чат записей: {h(show.registration_chat_title or show.registration_chat_id)}\n"
        if show.registration_chat_id else ""
    )

    text = (
        f"🎭 <b>{h(show.title)}</b>\n"
        f"👥 Команда: {h(show.team_name)}\n"
        f"📅 {format_local(show.show_date)}\n"
        f"🏙 {h(show.city)} | 📍 {h(show.location)}\n"
        f"🪑 Мест: {seats_left}/{show.max_seats}\n"
        f"{creator_label}"
        f"{registrar_label}"
        f"{registration_chat_label}"
    )
    if show.poster_text:
        text += f"\n📝 {h(show.poster_text)}"

    from aiogram.exceptions import TelegramBadRequest
    can_delete = tg_id in ADMIN_ID_LIST or bool(user and user.role == UserRole.admin)
    try:
        await callback.message.edit_text(text, reply_markup=None)
    except TelegramBadRequest:
        await callback.message.answer(text)
    data = await state.get_data()
    if data.get("reply_context") != "show" or data.get("current_show_id") != show_id:
        await state.update_data(reply_context="show", current_show_id=show_id)
        await callback.message.answer("⌨️ Быстрые действия для этого шоу", reply_markup=show_context_kb())


@router.callback_query(AdminShowActionCb.filter(F.action.in_({"promotion", "audience", "show_settings", "danger"})))
async def show_section(callback: CallbackQuery, callback_data: AdminShowActionCb, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await manageable_show(session, callback_data.show_id, db_user, is_super_admin)
    if show is None:
        await deny(callback, "⛔ Нет доступа к этому шоу.")
        return
    await callback.answer()
    titles = {
        "promotion": "📣 <b>Продвижение</b>",
        "audience": "📊 <b>Аналитика</b>",
        "show_settings": "⚙️ <b>Настройки шоу</b>",
        "danger": "⚠️ <b>Управление шоу</b>",
    }
    user = await crud.get_user_by_telegram_id(session, callback.from_user.id)
    can_delete = callback.from_user.id in ADMIN_ID_LIST or bool(user and user.role == UserRole.admin)
    await callback.message.edit_text(
        f"{titles[callback_data.action]}\n\n🎭 {h(show.title)}",
        reply_markup=show_section_kb(show, callback_data.action, can_delete=can_delete),
    )
    await state.update_data(
        current_show_id=show.id,
        reply_context="promotion" if callback_data.action == "promotion" else "show",
    )
    context_kb = promotion_context_kb() if callback_data.action == "promotion" else show_context_kb()
    await callback.message.answer("Навигация раздела:", reply_markup=context_kb)
