from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_notifications import _notify_show_change, _notify_date_change

async def _ask_edit_registrar(message: Message | CallbackQuery, state: FSMContext):
    data = await state.get_data()
    show_id = data.get("editing_show_id")
    async with AsyncSessionLocal() as session:
        show = await crud.get_show(session, show_id) if show_id else None
        organizers = await crud.get_all_organizers(session)
        teams = await crud.list_teams(session)

    team = next((item for item in teams if show and item.name == show.team_name), None)
    team_usernames = normalize_telegram_username_list(team.members) if team and team.members else []
    organizer_usernames = {u.username.lower() for u in organizers if u.username}
    team_usernames = [username for username in team_usernames if username not in organizer_usernames]

    lines = []
    for idx, u in enumerate(organizers, start=1):
        if u.username:
            lines.append(f"{idx}. <a href=\"https://t.me/{u.username}\">{h(u.first_name or ('@'+u.username))}</a>")
        else:
            lines.append(f"{idx}. {h(u.first_name or ('id'+str(u.telegram_id)))}")
    if team_usernames:
        lines.append("\n<b>Участники команды:</b>")
        lines.extend(f'• <a href="https://t.me/{username}">@{username}</a>' for username in team_usernames)

    text = "Выбери ответственного за записи (или пропусти):\n\n" + "\n".join(lines)
    if show and (show.registrar or show.registrar_username):
        current_name = _registrar_name(show.registrar, show.registrar_username)
        text += f"\n\nТекущий: <b>{h(current_name)}</b>"

    kb = InlineKeyboardBuilder()
    for u in organizers:
        label = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        kb.button(text=label, callback_data=f"registrar:{u.id}")
    for username in team_usernames:
        kb.button(text=f"@{username}", callback_data=f"registrar:username:{username}")
    kb.button(text="✍️ Ввести Telegram ник", callback_data="registrar:manual")
    kb.button(text="Пропустить (через бот)", callback_data="registrar:0")
    kb.button(text="◀️ К шоу", callback_data=AdminShowActionCb(action="open", show_id=show_id).pack())
    kb.adjust(1)

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@router.callback_query(EditShowFSM.new_value, lambda q: q.data and q.data.startswith("registrar:"))
async def edit_process_registrar_choice(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession,
    db_user=None, is_super_admin: bool = False,
):
    await callback.answer()
    data = await state.get_data()
    if data.get("editing_field") != "registrar_id":
        return
    _, raw = callback.data.split(":", 1)
    if raw == "manual":
        await callback.message.edit_text(
            "Введи Telegram ник ответственного в формате @username или username:\n\nНапример: @sergey",
            reply_markup=fsm_cancel_kb(),
        )
        return
    if raw.startswith("username:"):
        username = normalize_telegram_username(raw.removeprefix("username:"))
        user = await crud.get_user_by_username(session, username) if username else None
        registrar_value = {"registrar_id": user.id if user else None, "registrar_username": username}
    else:
        try:
            value = int(raw)
        except ValueError:
            value = None
    if not raw.startswith("username:") and value == 0:
        registrar_value = {"registrar_id": None, "registrar_username": None}
    elif not raw.startswith("username:"):
        user = await crud.get_user_by_id(session, value) if value else None
        registrar_value = {
            "registrar_id": value,
            "registrar_username": user.username.lower() if user and user.username else None,
        }
    await _apply_edit(
        callback.message, state, session, registrar_value,
        db_user=db_user, is_super_admin=is_super_admin,
    )


@router.message(EditShowFSM.new_value, F.photo)
async def save_edit_photo(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot, public_bot: Bot,
    db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    if data.get("editing_field") != "poster_file_id":
        await message.answer("Ожидался текст. Введи текстовое значение:")
        return
    await _apply_edit(
        message, state, session, message.photo[-1].file_id, bot=bot, public_bot=public_bot,
        db_user=db_user, is_super_admin=is_super_admin,
    )


@router.message(EditShowFSM.new_value, F.text)
async def save_edit_text(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot, public_bot: Bot,
    db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    field = data.get("editing_field")
    raw = message.text.strip()

    if field == "show_date":
        try:
            local_value = datetime.strptime(raw, "%d.%m.%Y %H:%M")
        except ValueError:
            await message.answer("Неверный формат. Введи как ДД.ММ.ГГГГ ЧЧ:ММ:")
            return
        if local_value.replace(tzinfo=local_now().tzinfo) <= local_now():
            await message.answer("❌ Дата в прошлом. Введи будущую дату:")
            return
        value = local_naive_to_utc(local_value)
    elif field == "max_seats":
        try:
            value = int(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Введи положительное целое число:")
            return
    elif field == "title":
        if len(raw) < 2:
            await message.answer("Название слишком короткое (минимум 2 символа):")
            return
        value = raw
    elif field == "team_name":
        if len(raw) < 2:
            await message.answer("Название команды слишком короткое (минимум 2 символа):")
            return
        value = raw
    elif field == "poster_text":
        if raw == "/skip":
            value = None
        else:
            error = _validate_poster_text(raw)
            if error:
                await message.answer(error)
                return
            value = raw
    elif field == "location_url":
        if raw == "/skip":
            value = None
        elif not _is_google_maps_url(raw):
            await message.answer(
                "Это не ссылка на Google Maps. Введи корректную ссылку или /skip чтобы убрать:"
            )
            return
        else:
            value = raw
    elif field == "registrar_id":
        if raw.lower() in {"/skip", "skip"}:
            value = {"registrar_id": None, "registrar_username": None}
        else:
            username = normalize_telegram_username(raw)
            if not username:
                await message.answer("Неверный Telegram ник. Введи @username, например @sergey:")
                return
            async with AsyncSessionLocal() as session_lookup:
                user = await crud.get_user_by_username(session_lookup, username)
                value = {
                    "registrar_id": user.id if user else None,
                    "registrar_username": username,
                }
    else:
        await state.clear()
        await deny(message, "⛔ Недоступное поле.")
        return

    notify_fields = {"show_date", "title", "location", "city"}
    await _apply_edit(message, state, session, value, bot=bot if field in notify_fields else None,
                      public_bot=public_bot if field in notify_fields else None,
                      db_user=db_user, is_super_admin=is_super_admin)


async def _apply_edit(
    message: Message, state: FSMContext, session: AsyncSession, value,
    bot: Bot = None, public_bot: Bot = None, db_user=None, is_super_admin: bool = False,
):
    data = await state.get_data()
    show_id = data["editing_show_id"]
    field = data["editing_field"]
    should_notify = bool(data.get("edit_notify"))
    old_show = await manageable_show(session, show_id, db_user, is_super_admin)
    if old_show is None:
        await state.clear()
        await deny(message, "⛔ Нет доступа к этому шоу.")
        return
    await state.clear()
    old_value = getattr(old_show, field, None)
    update_fields = value if field in {"registrar_id", "location"} and isinstance(value, dict) else {field: value}
    show = await crud.update_show(session, show_id, **update_fields)

    logger.info("updated show id=%s field=%s by admin=%s", show_id, field, message.from_user.id)

    if show is None:
        await message.answer("Шоу не найдено.")
        return

    # When poster is updated, re-cache for public bot
    if field == "poster_file_id" and value and bot and public_bot:
        pub_file_id = await cache_poster_for_public_bot(bot, public_bot, value, message.from_user.id)
        if pub_file_id:
            async with AsyncSessionLocal() as extra_session:
                await crud.update_show(extra_session, show_id, pub_poster_file_id=pub_file_id)

    await state.update_data(reply_context="show", current_show_id=show_id)
    await message.answer("✅ Поле обновлено!", reply_markup=show_context_kb())

    if should_notify and field in {"show_date", "title", "location", "city"} and old_value is not None and public_bot and bot:
        await _notify_show_change(show, field, old_value, bot, public_bot)
