from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _manageable_api_show, _record_audit, _required_text, _show_id


async def miniapp_show_tasks(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if show.show_date < utc_now():
            return web.json_response({"items": [], "registeredUsers": 0})
        registrations = await crud.get_registered_users_for_show(session, show_id)
        occupied = await crud.count_active_registrations(session, show_id)
        pending_manual = await crud.get_pending_manual_attendees_for_reminder(session, show_id, limit=100)
        announced = await crud.has_any_announcement_been_sent(session, show_id)
        tasks = []
        if not announced: tasks.append({"key": "announcement", "label": "Опубликовать анонс", "count": 1})
        if not show.registrar_id and not show.registrar_username:
            tasks.append({"key": "show_responsible", "label": "Указать ответственного", "description": "Зрителям некому написать по вопросам записи", "count": 1})
        if (
            announced
            and show.is_active
            and show.show_date - utc_now() <= REANNOUNCEMENT_WINDOW
            and occupied < show.max_seats * REANNOUNCEMENT_OCCUPANCY_THRESHOLD
        ):
            tasks.append({
                "key": "repeat_announcement",
                "label": "Повторить анонс",
                "description": f"До шоу меньше 3 дней · заполнено {occupied} из {show.max_seats}",
                "count": 1,
            })
        if not show.registration_chat_id: tasks.append({"key": "registration_chat", "label": "Подключить рабочий чат", "count": 1})
        if pending_manual: tasks.append({"key": "manual_notifications", "label": "Уведомить добавленных вручную", "count": len(pending_manual)})
        return web.json_response({"items": tasks, "registeredUsers": len(registrations)})


async def miniapp_remind_viewers(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if not show.is_active:
            raise web.HTTPConflict(text=json.dumps({"error": "show_cancelled"}), content_type="application/json")
        users = await crud.get_registered_users_for_show(session, show_id)
        title, date_label, location, city = show.title, format_local(show.show_date), show.location, show.city
    text = f"🔔 Напоминание!\n\nТы записан(а) на шоу <b>{h(title)}</b>\n📅 {date_label}\n📍 {h(location)}, {h(city)}"
    bot = request.app[PUBLIC_BOT_KEY]
    sent = failed = 0
    for user in users:
        try:
            await send_with_retry(bot.send_message, user.telegram_id, text)
            sent += 1
        except Exception:
            failed += 1
    await _record_audit(request, "show.reminders_sent", "show", show_id, {"sent": sent, "failed": failed})
    return web.json_response({"sent": sent, "failed": failed})


async def _verified_registration_chat(bot: Bot, target_raw: str):
    target_raw = target_raw.replace("−", "-")
    target: str | int = target_raw
    if not target_raw.startswith("@"):
        try: target = int(target_raw)
        except ValueError: raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "target"}), content_type="application/json")
    try:
        chat = await bot.get_chat(target)
        bot_user = await bot.get_me()
        member = await bot.get_chat_member(chat.id, bot_user.id)
        status = getattr(member.status, "value", member.status)
        if status not in {ChatMemberStatus.MEMBER.value, ChatMemberStatus.ADMINISTRATOR.value, ChatMemberStatus.CREATOR.value}:
            raise web.HTTPConflict(text=json.dumps({"error": "bot_not_in_chat"}), content_type="application/json")
        chat_type = getattr(chat.type, "value", chat.type)
        if chat_type == ChatType.CHANNEL.value and status not in {ChatMemberStatus.ADMINISTRATOR.value, ChatMemberStatus.CREATOR.value}:
            raise web.HTTPConflict(text=json.dumps({"error": "bot_cannot_post"}), content_type="application/json")
        if chat_type == ChatType.CHANNEL.value and getattr(member, "can_post_messages", True) is False:
            raise web.HTTPConflict(text=json.dumps({"error": "bot_cannot_post"}), content_type="application/json")
    except (TelegramBadRequest, TelegramForbiddenError):
        raise web.HTTPConflict(text=json.dumps({"error": "chat_unavailable"}), content_type="application/json")
    display_name = getattr(chat, "title", None) or getattr(chat, "username", None) or target_raw
    return chat, display_name


async def miniapp_verify_registration_chat(request: web.Request) -> web.Response:
    data = await _json_body(request)
    if any(key not in {"target"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    target_raw = _required_text(data, "target", 128)
    chat, display_name = await _verified_registration_chat(request.app[ADMIN_BOT_KEY], target_raw)
    return web.json_response({"id": chat.id, "title": display_name})


async def miniapp_registration_chats(request: web.Request) -> web.Response:
    async with AsyncSessionLocal() as session:
        chats = await crud.get_registration_chats(session, request["miniapp_user_id"])
    return web.json_response({"items": [
        {
            "id": item.chat_id,
            "title": item.title,
            "username": item.username,
            "type": item.chat_type,
        }
        for item in chats
    ]})


async def miniapp_registration_chat(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if any(key not in {"target", "nameMode"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    target_raw = _required_text(data, "target", 128)
    if data.get("nameMode", "full") not in {"short", "full"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "nameMode"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        title = show.title
    bot = request.app[ADMIN_BOT_KEY]
    chat, display_name = await _verified_registration_chat(bot, target_raw)
    try:
        await send_with_retry(bot.send_message, chat.id, f"✅ Чат подключён к шоу «{h(title)}». Здесь будут появляться новые записи.")
    except (TelegramBadRequest, TelegramForbiddenError):
        raise web.HTTPConflict(text=json.dumps({"error": "chat_unavailable"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        await crud.update_show(session, show_id, registration_chat_id=chat.id, registration_chat_title=display_name, registration_chat_name_mode="full")
    return web.json_response({"id": chat.id, "title": display_name, "nameMode": "full"})


async def miniapp_clear_registration_chat(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        chat_id = show.registration_chat_id
        title = show.title
    notified = False
    if chat_id:
        try:
            await send_with_retry(
                request.app[ADMIN_BOT_KEY].send_message,
                chat_id,
                f"🔕 Чат вручную отключён от шоу «{h(title)}». Новые записи сюда больше не будут приходить.",
            )
            notified = True
        except (TelegramBadRequest, TelegramForbiddenError):
            logging.getLogger(__name__).warning("registration chat unavailable while disconnecting show_id=%s", show_id)
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        if chat_id:
            await crud.clear_registration_chat_if_matches(session, show_id, chat_id)
    return web.json_response({"id": show_id, "notified": notified})


async def miniapp_confirm_manual_notifications(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        count = await crud.confirm_manual_attendees_notified(session, show_id)
    return web.json_response({"confirmed": count})


async def miniapp_restore_show(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if show.is_active:
            raise web.HTTPConflict(text=json.dumps({"error": "already_active"}), content_type="application/json")
        await crud.update_show(session, show_id, is_active=True)
    await _record_audit(request, "show.restored", "show", show_id)
    return web.json_response({"id": show_id, "isActive": True})


async def miniapp_delete_show(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if show.is_active and not request.get("miniapp_is_super_admin", False):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "super_admin_required"}), content_type="application/json",
            )
        if not await crud.delete_show(session, show_id):
            raise web.HTTPConflict(text=json.dumps({"error": "delete_rejected"}), content_type="application/json")
    await _record_audit(request, "show.deleted", "show", show_id)
    return web.json_response({"id": show_id})
