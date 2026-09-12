from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()
from admin_bot.handlers.shows_listing import _render_shows_list
from admin_bot.handlers.shows_promotion import _show_deep_link

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, command: CommandObject, db_user=None, is_super_admin: bool = False):
    from admin_bot.handlers.onboarding import start_onboarding
    user = await crud.upsert_user(
        session, message.from_user.id, message.from_user.username,
        message.from_user.first_name, message.from_user.last_name,
    )
    payload = command.args or ""
    if payload.startswith("door_"):
        try:
            show_id = int(payload.removeprefix("door_"))
        except ValueError:
            show_id = 0
        from admin_bot.security import checkin_accessible_show
        show = await checkin_accessible_show(session, show_id, db_user or user, is_super_admin)
        if show is None or not show.checkin_enabled:
            await message.answer("⛔ Доступ к режиму входа недействителен.")
            return
        await message.answer(
            f"🚪 <b>Вход: {h(show.title)}</b>\n\nНажми «Открыть панель управления» ниже. "
            "В Mini App откроется страница отметки пришедших. Доступ выдан только к этому шоу.",
            reply_markup=miniapp_launch_kb(),
        )
        return
    if not user.onboarding_done:
        await start_onboarding(message)
        return
    await message.answer(
        "👋 Привет! Открой панель управления:",
        reply_markup=miniapp_launch_kb(),
    )
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@router.message(F.text.in_({"🌐 Панель управления", "🚀 Открыть Mini App"}))
@router.message(Command("app"))
async def cmd_miniapp(message: Message, state: FSMContext):
    await state.clear()
    keyboard = miniapp_launch_kb()
    if keyboard is None:
        await message.answer("Mini App пока не настроен.")
        return
    await message.answer("🌐 Панель управления", reply_markup=keyboard)


@router.message(Command("home"))
async def cmd_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=main_menu_kb())


@router.message(F.text == "🏠 Главное меню")
async def quick_home(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🏠 Главное меню", reply_markup=main_menu_kb())


@router.message(F.text == "❌ Отмена")
async def quick_cancel(message: Message, state: FSMContext):
    current = await state.get_state()
    await state.clear()
    text = "❌ Действие отменено." if current else "Сейчас нет активного действия."
    await message.answer(text, reply_markup=main_menu_kb())


async def _quick_show(message: Message, state: FSMContext, session: AsyncSession, db_user, is_super_admin):
    show_id = (await state.get_data()).get("current_show_id")
    show = await manageable_show(session, show_id, db_user, is_super_admin) if show_id else None
    if show is None:
        await state.clear()
        await message.answer("Сначала открой шоу из афиши.", reply_markup=main_menu_kb())
    return show


@router.message(F.text == "👥 Записи")
async def quick_show_registrations(
    message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    show = await _quick_show(message, state, session, db_user, is_super_admin)
    if show:
        from admin_bot.handlers.registrations import _render_registrations
        await _render_registrations(message, show.id, session, edit=False, is_super_admin=is_super_admin, db_user=db_user)
        await state.update_data(reply_context="registrations")
        await message.answer("Действия с записями:", reply_markup=registrations_context_kb())


@router.message(F.text == "📣 Продвижение")
async def quick_show_promotion(
    message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    await state.clear()
    await message.answer("Публикация и продвижение афиш находятся в Mini App.", reply_markup=miniapp_launch_kb())


@router.message(F.text == "◀️ К шоу")
async def quick_back_to_show(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _quick_show(message, state, session, db_user, is_super_admin)
    if show is None:
        return
    await state.update_data(reply_context="show", current_show_id=show.id)
    await message.answer(f"🎭 <b>{h(show.title)}</b>", reply_markup=show_context_kb())


@router.message(F.text == "👁 Превью")
async def quick_promotion_preview(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _quick_show(message, state, session, db_user, is_super_admin)
    if show is None:
        return
    text = build_announcement_text(show)
    if show.poster_file_id:
        await message.answer_photo(show.poster_file_id, caption=f"👁 <b>Превью анонса:</b>\n\n{text}", reply_markup=promotion_context_kb())
    else:
        await message.answer(f"👁 <b>Превью анонса:</b>\n\n{text}", reply_markup=promotion_context_kb())


@router.message(F.text == "📢 Анонс")
async def quick_promotion_announce(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _quick_show(message, state, session, db_user, is_super_admin)
    if show is None:
        return
    if await crud.has_any_announcement_been_sent(session, show.id):
        await message.answer("Анонс уже был отправлен.", reply_markup=promotion_context_kb())
        return
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подтвердить отправку", callback_data=AdminShowActionCb(action="announce", show_id=show.id).pack())
    await message.answer("Отправить анонс в основной канал?", reply_markup=kb.as_markup())


@router.message(F.text == "🔗 Ссылка и QR")
async def quick_promotion_link(message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False):
    show = await _quick_show(message, state, session, db_user, is_super_admin)
    if show is None:
        return
    link = _show_deep_link(show.id)
    qr = qrcode.QRCode(box_size=8, border=3)
    qr.add_data(link)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    await message.answer_photo(
        BufferedInputFile(buffer.getvalue(), filename="show-link.png"),
        caption=f"🔗 <b>Ссылка на запись</b>\n<code>{link}</code>",
        reply_markup=promotion_context_kb(),
    )


@router.message(F.text == "✏️ Редактировать")
async def quick_show_edit(
    message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    await state.clear()
    await message.answer("Редактирование афиши находится в Mini App.", reply_markup=miniapp_launch_kb())


@router.message(F.text == "◀️ К списку шоу")
async def quick_back_to_shows(
    message: Message, state: FSMContext, session: AsyncSession, db_user=None, is_super_admin: bool = False,
):
    await state.clear()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(message, state, session, edit=False, can_manage=_can_manage(is_super_admin, db_user))


@router.message(Command("create_show"))
@router.message(F.text == "🆕 Создать")
@router.callback_query(F.data == "admin_create_show")
async def cmd_create_show(event, state: FSMContext):
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    await state.clear()
    await msg.answer(
        "Создание афиши перенесено в Mini App — там быстрее заполнять поля и сразу видно предпросмотр.",
        reply_markup=miniapp_launch_kb(),
    )


@router.message(F.text == "📋 Афиша")
@router.message(Command("shows"))
async def cmd_shows_message(message: Message, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.clear()
    from admin_bot.handlers.registrations import _can_manage
    await _render_shows_list(message, state, session, edit=False, can_manage=_can_manage(is_super_admin, db_user))


@router.message(F.text == "🎭 Моё")
@router.message(Command("my"))
@router.callback_query(F.data == "admin_my_shows")
async def cmd_my_shows(event, state: FSMContext, session: AsyncSession, is_super_admin: bool = False, db_user=None):
    await state.clear()
    msg = event if isinstance(event, Message) else event.message
    if isinstance(event, CallbackQuery):
        await event.answer()
    tg_id = event.from_user.id
    from admin_bot.handlers.registrations import _can_manage
    can_manage = _can_manage(is_super_admin, db_user)

    shows = await crud.list_shows_by_creator(session, tg_id)

    if not shows:
        text = "У тебя пока нет созданных шоу."
    else:
        text = f"🎭 <b>Мои шоу</b> ({len(shows)}):"

    kb = shows_list_kb(shows, can_manage=can_manage)
    if isinstance(event, Message):
        await msg.answer(text, reply_markup=kb)
    else:
        await msg.edit_text(text, reply_markup=kb)


@router.message(F.text == "⚙️ Настройки")
@router.message(Command("settings"))
async def cmd_settings(message: Message, state: FSMContext, db_user=None, is_super_admin: bool = False):
    await state.clear()
    await message.answer("Настройки команд, площадок и доступа находятся в Mini App.", reply_markup=miniapp_launch_kb())


@router.callback_query(F.data == "admin_settings")
async def back_to_settings(callback: CallbackQuery, state: FSMContext, db_user=None, is_super_admin: bool = False):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        "Настройки команд, площадок и доступа находятся в Mini App.",
        reply_markup=miniapp_launch_kb(),
    )
