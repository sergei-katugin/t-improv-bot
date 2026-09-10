from __future__ import annotations
from admin_bot.handlers.shows_shared import *

router = Router()

async def _make_calendar(session: AsyncSession) -> RuCalendar:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from db.models import Show, User
    now = local_now()
    lower_bound = local_naive_to_utc(datetime(now.year - 1, 1, 1))
    upper_bound = local_naive_to_utc(datetime(now.year + 2, 1, 1))
    result = await session.execute(
        select(Show)
        .options(selectinload(Show.creator))
        .where(Show.show_date >= lower_bound, Show.show_date < upper_bound)
    )
    shows = result.scalars().all()
    busy: dict[_date, list[str]] = {}
    for s in shows:
        d = local_date(s.show_date)
        creator = s.creator
        if creator:
            name = creator.first_name or creator.username or f"id{creator.telegram_id}"
        else:
            name = "?"
        busy.setdefault(d, []).append(f"{s.title} ({name})")
    return RuCalendar(busy)


def _preview_from_data(data: dict) -> str:
    location = data.get("location", "")
    location_url = data.get("location_url")
    city = data.get("city", "")
    if location_url:
        location_line = f'📍 <a href="{h(location_url)}">{h(location)}</a>, {h(city)}'
    else:
        location_line = f"📍 {h(location)}, {h(city)}"

    show_date = data.get("show_date")
    if show_date:
        date_str = _fmt_date(show_date)
    else:
        date_str = data.get("show_date_str", "")

    bot_username = settings.PUBLIC_BOT_USERNAME.lstrip("@")
    registration_targets = (
        f'<b>через бота</b> '
        f'<a href="https://t.me/{bot_username}">@{h(bot_username)}</a>'
    )
    registrar_username = data.get("registrar_username")
    if registrar_username:
        registrar_username = registrar_username.lstrip("@")
        registration_targets += (
            f' или у <a href="https://t.me/{registrar_username}">@{h(registrar_username)}</a>'
        )
    poster = data.get("poster_text") or ""
    title = h(data.get("title", ""))
    team_name = data.get("team_name")
    header = (
        f"🎭 <b>Команда {h(team_name)} представляет шоу {title}</b>"
        if team_name else f"🎭 <b>Шоу {title}</b>"
    )
    lines = [
        header,
        f"📅 {date_str}",
        location_line,
        f"👥 Записаться тут: {registration_targets}",
    ]
    if poster:
        lines += ["", h(poster)]
    return "\n".join(lines)


async def _show_confirm(message: Message, state: FSMContext, *, edit: bool = False):
    data = await state.get_data()
    total = data.get("_total", _TOTAL_STEPS_PRESET)
    await state.set_state(CreateShowFSM.confirm)

    preview = _preview_from_data(data)
    kb = confirm_with_back_kb(
        "admin_confirm_create",
        "admin_cancel_create",
        checkin_enabled=data.get("checkin_enabled", False),
        feedback_enabled=data.get("feedback_enabled", True),
    )
    header = f"{_progress(total, total)}👁 <b>Так будет выглядеть анонс:</b>\n\n"

    file_id = data.get("poster_file_id")
    if edit and message.photo:
        await message.edit_caption(caption=header + preview, reply_markup=kb)
    elif edit:
        await message.edit_text(header + preview, reply_markup=kb)
    elif file_id:
        await message.answer_photo(
            photo=file_id,
            caption=header + preview,
            reply_markup=kb,
        )
    else:
        await message.answer(header + preview, reply_markup=kb)


@router.callback_query(CreateShowFSM.confirm, F.data.in_({"create_toggle_checkin", "create_toggle_feedback"}))
async def toggle_create_option(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    field = "checkin_enabled" if callback.data == "create_toggle_checkin" else "feedback_enabled"
    value = not bool(data.get(field, False))
    await state.update_data(**{field: value})
    await callback.answer("Включено" if value else "Выключено")
    await _show_confirm(callback.message, state, edit=True)


async def _ask_registrar(message: Message, state: FSMContext, bot: Bot):
    """Prompt to optionally choose a registrar (organizer/admin) or skip."""
    await state.set_state(CreateShowFSM.registrar)
    # fetch organizers/admins
    data = await state.get_data()
    async with AsyncSessionLocal() as session:
        organizers = await crud.get_all_organizers(session)
        team = await crud.get_team(session, data.get("team_id")) if data.get("team_id") else None

    team_usernames = normalize_telegram_username_list(team.members) if team and team.members else []
    team_usernames = team_usernames or []
    organizer_usernames = {u.username.lower() for u in organizers if u.username}
    team_usernames = [username for username in team_usernames if username not in organizer_usernames]

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    # build message with clickable t.me links when username exists
    lines = []
    for idx, u in enumerate(organizers, start=1):
        if u.username:
            lines.append(f"{idx}. <a href=\"https://t.me/{u.username}\">{h(u.first_name or ('@'+u.username))}</a>")
        else:
            lines.append(f"{idx}. {h(u.first_name or ('id'+str(u.telegram_id)))}")
    if team_usernames:
        lines.append("\n<b>Участники выбранной команды:</b>")
        lines.extend(
            f'• <a href="https://t.me/{username}">@{username}</a>'
            for username in team_usernames
        )

    text = "Выбери ответственного за записи (опционально):\n\n" + "\n".join(lines)

    kb = InlineKeyboardBuilder()
    for u in organizers:
        label = u.first_name or (('@' + u.username) if u.username else f'id{u.telegram_id}')
        kb.button(text=label, callback_data=f"registrar:{u.id}")
    for username in team_usernames:
        kb.button(text=f"@{username}", callback_data=f"registrar:username:{username}")
    kb.button(text="✍️ Ввести Telegram ник", callback_data="registrar:manual")
    kb.button(text="Пропустить (через бот)", callback_data="registrar:0")
    kb.button(text="◀️ Назад", callback_data="fsm_back")
    kb.adjust(1)
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
