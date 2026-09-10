from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_create_confirm import _make_calendar
from admin_bot.handlers.shows_create_confirm import _show_confirm
from admin_bot.handlers.shows_create_team import _time_kb

@router.callback_query(F.data == "fsm_back")
async def fsm_back(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    await callback.answer()
    current = await state.get_state()
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)

    if current == CreateShowFSM.title:
        await state.set_state(CreateShowFSM.team_name)
        await callback.message.edit_text(
            f"{_progress(1)}Выбери команду из списка или введи своё название:",
            reply_markup=team_kb(),
        )

    elif current == CreateShowFSM.show_date:
        await state.set_state(CreateShowFSM.title)
        await callback.message.edit_text(f"{_progress(2)}Введи название шоу:", reply_markup=fsm_cancel_kb())

    elif current == CreateShowFSM.select_time:
        now = local_now()
        await state.set_state(CreateShowFSM.show_date)
        await callback.message.edit_text(
            f"{_progress(3)}Выбери дату шоу:",
            reply_markup=await (await _make_calendar(session)).start_calendar(year=now.year, month=now.month),
        )

    elif current == CreateShowFSM.select_venue:
        await state.set_state(CreateShowFSM.select_time)
        await callback.message.edit_text(
            f"{_progress(3)}Выбери время начала:",
            reply_markup=_time_kb(),
        )

    elif current == CreateShowFSM.location:
        venues = await crud.list_venues(session)
        await state.set_state(CreateShowFSM.select_venue)
        await callback.message.edit_text(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))

    elif current == CreateShowFSM.location_url:
        await state.set_state(CreateShowFSM.location)
        await callback.message.edit_text(
            f"{_progress(4, _TOTAL_STEPS_CUSTOM)}Введи название площадки/театра:",
            reply_markup=fsm_cancel_kb(),
        )

    elif current in (CreateShowFSM.select_city, CreateShowFSM.city):
        await state.set_state(CreateShowFSM.location_url)
        await callback.message.edit_text(
            f"{_progress(5, _TOTAL_STEPS_CUSTOM)}Введи ссылку на Google Maps для этой площадки:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_location_url"),
        )

    elif current == CreateShowFSM.max_seats:
        await state.set_state(CreateShowFSM.select_city)
        await callback.message.edit_text(
            f"{_progress(6, _TOTAL_STEPS_CUSTOM)}Выбери город:",
            reply_markup=city_kb(),
        )

    elif current == CreateShowFSM.poster_text:
        if total == _TOTAL_STEPS_PRESET:
            venues = await crud.list_venues(session)
            await state.set_state(CreateShowFSM.select_venue)
            await callback.message.edit_text(f"{_progress(4)}Выбери площадку:", reply_markup=venue_kb(venues))
        else:
            await state.set_state(CreateShowFSM.max_seats)
            await callback.message.edit_text(
                f"{_progress(7, _TOTAL_STEPS_CUSTOM)}Введи количество мест (только цифры):",
                reply_markup=fsm_cancel_kb(),
            )

    elif current == CreateShowFSM.poster_image:
        await state.set_state(CreateShowFSM.poster_text)
        await callback.message.edit_text(
            f"{_progress(total - 1, total)}Введи текст афиши:\n⚠️ Не указывай дату, время и адрес — они уже есть в отдельных полях.",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_text"),
        )

    elif current == CreateShowFSM.registrar:
        await state.set_state(CreateShowFSM.poster_image)
        await callback.message.answer(
            f"{_progress(total - 1, total)}Отправь изображение афиши:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
        )

    elif current == CreateShowFSM.confirm:
        await state.set_state(CreateShowFSM.poster_image)
        await callback.message.answer(
            f"{_progress(total - 1, total)}Отправь изображение афиши:",
            reply_markup=fsm_skip_cancel_kb("fsm_skip_poster_image"),
        )

    else:
        await callback.message.answer("Это первый шаг, назад некуда.")


@router.callback_query(F.data == "fsm_cancel")
async def fsm_cancel(callback: CallbackQuery, state: FSMContext, is_super_admin: bool = False):
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.edit_text("❌ Создание шоу отменено.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.callback_query(CreateShowFSM.registrar, lambda q: q.data and q.data.startswith("registrar:"))
async def process_registrar_choice(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    _, raw = callback.data.split(":", 1)
    if raw == "manual":
        await callback.message.edit_text(
            "Введи Telegram ник ответственного в формате @username или username:\n\nНапример: @sergey",
            reply_markup=fsm_cancel_kb(),
        )
        return
    if raw.startswith("username:"):
        username = normalize_telegram_username(raw.split(":", 1)[1])
        if not username:
            await callback.message.answer("Некорректный Telegram ник.")
            return
        async with AsyncSessionLocal() as session:
            user = await crud.get_user_by_username(session, username)
        await state.update_data(
            registrar_id=user.id if user else None,
            registrar_username=username,
            registrar_name=f"@{username}",
        )
        await _show_confirm(callback.message, state)
        return
    try:
        uid = int(raw)
    except ValueError:
        uid = 0
    if uid == 0:
        await state.update_data(registrar_id=None, registrar_username=None, registrar_name=None)
    else:
        # store chosen registrar id and name for preview
        async with AsyncSessionLocal() as session:
            u = await crud.get_user_by_id(session, uid) if hasattr(crud, 'get_user_by_id') else None
        name = None
        if u:
            name = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        await state.update_data(
            registrar_id=uid,
            registrar_username=u.username.lower() if u and u.username else None,
            registrar_name=name,
        )
    # proceed to confirm
    await _show_confirm(callback.message, state)


@router.message(CreateShowFSM.registrar, F.text)
async def process_manual_registrar_input(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if raw.lower() in {"/skip", "skip"}:
        await state.update_data(registrar_id=None, registrar_username=None, registrar_name=None)
        await _show_confirm(message, state)
        return

    username = normalize_telegram_username(raw)
    if not username:
        await message.answer("Неверный Telegram ник. Введи @username, например @sergey:", reply_markup=fsm_cancel_kb())
        return

    async with AsyncSessionLocal() as session:
        user = await crud.get_user_by_username(session, username)
        await state.update_data(
            registrar_id=user.id if user else None,
            registrar_username=username,
            registrar_name=f"@{username}",
        )

    await _show_confirm(message, state)


@router.callback_query(CreateShowFSM.confirm, F.data == "admin_confirm_create")
async def confirm_create(callback: CallbackQuery, state: FSMContext, bot: Bot, public_bot: Bot, session: AsyncSession, is_super_admin: bool = False):
    data = await state.get_data()
    await callback.answer()

    tg_id = callback.from_user.id
    user = await crud.get_user_by_telegram_id(session, tg_id)
    if user is None:
        user = await crud.upsert_user(session, tg_id, callback.from_user.username,
                                      callback.from_user.first_name, callback.from_user.last_name)
    show = await crud.create_show(
        session,
        title=data["title"],
        team_name=data["team_name"],
        show_date=data["show_date"],
        location=data["location"],
        location_url=data.get("location_url"),
        city=data["city"],
        poster_text=data.get("poster_text"),
        poster_file_id=data.get("poster_file_id"),
        max_seats=data["max_seats"],
        creator_id=user.id,
        registrar_id=data.get("registrar_id"),
        registrar_username=data.get("registrar_username"),
        checkin_enabled=bool(data.get("checkin_enabled", False)),
        feedback_enabled=bool(data.get("feedback_enabled", False)),
    )
    logger.info("admin %s created show id=%s title=%s", tg_id, show.id, data.get('title'))

    await state.clear()
    from admin_bot.handlers.registrations import RegistrationChatFSM
    from admin_bot.keyboards.reply import registration_channel_picker_kb
    await state.set_state(RegistrationChatFSM.chat)
    await state.update_data(show_id=show.id, current_show_id=show.id, reply_context="flow")
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer(
        f"✅ Шоу <b>{h(data['title'])}</b> создано и пока нигде не опубликовано.",
        reply_markup=registration_channel_picker_kb(),
    )
    await callback.message.answer(
        "Последний необязательный шаг: выбери рабочий канал для новых записей. "
        "Telegram сам добавит этого бота с правом публикации. Можно пропустить и подключить позже.",
    )
    # Cache poster for public bot so it can display it via deep links
    if show.poster_file_id:
        pub_file_id = await cache_poster_for_public_bot(bot, public_bot, show.poster_file_id, tg_id)
        if pub_file_id:
            async with AsyncSessionLocal() as extra_session:
                await crud.update_show(extra_session, show.id, pub_poster_file_id=pub_file_id)


@router.callback_query(CreateShowFSM.confirm, F.data == "admin_cancel_create")
async def cancel_create(callback: CallbackQuery, state: FSMContext, is_super_admin: bool = False):
    await state.clear()
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("❌ Создание отменено.", reply_markup=main_menu_kb())
