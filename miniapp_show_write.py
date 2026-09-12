from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _record_audit, _show_fields










async def miniapp_create_show(request: web.Request) -> web.Response:
    fields = _show_fields(await _json_body(request), require_all=True)
    async with AsyncSessionLocal() as session:
        conflict = await session.scalar(select(Show).where(
            Show.is_active == True,
            Show.show_date.between(fields["show_date"] - timedelta(hours=3), fields["show_date"] + timedelta(hours=3)),
            or_(Show.team_name == fields["team_name"], Show.location == fields["location"]),
        ).limit(1))
        if conflict:
            raise web.HTTPConflict(text=json.dumps({"error": "scheduling_conflict", "field": "showDateLocal", "message": f"Конфликт с афишей «{conflict.title}»: та же команда или площадка в пределах трёх часов"}), content_type="application/json")
        username = fields.get("registrar_username")
        registrar = await crud.get_user_by_username(session, str(username)) if username else None
        show = await crud.create_show(
            session,
            **fields,
            poster_file_id=None,
            creator_id=request["miniapp_user_id"],
            registrar_id=registrar.id if registrar else None,
        )
        return web.json_response({"id": show.id}, status=201)


async def miniapp_update_show(request: web.Request) -> web.Response:
    try:
        show_id = int(request.match_info["show_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    notify = data.pop("notify", False)
    if not isinstance(notify, bool):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "notify"}), content_type="application/json")
    fields = _show_fields(data, require_all=False)
    if not fields:
        raise web.HTTPBadRequest(text=json.dumps({"error": "empty_update"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        db_user = await session.get(User, request["miniapp_user_id"])
        show = await crud.get_show(session, show_id)
        if show is None or not can_manage_owned(show.creator_id, db_user, request["miniapp_is_admin"]):
            raise web.HTTPNotFound()
        from checkin_service import arrival_stats
        await session.refresh(show, with_for_update=True)
        if fields.get("checkin_mode", show.checkin_mode) != show.checkin_mode and (await arrival_stats(session, show))["arrived"]:
            raise web.HTTPConflict(text="Нельзя менять режим после начала входа")
        if "registrar_username" in fields:
            username = fields["registrar_username"]
            registrar = await crud.get_user_by_username(session, str(username)) if username else None
            fields["registrar_id"] = registrar.id if registrar else None
        effective_date = fields.get("show_date", show.show_date)
        effective_team = fields.get("team_name", show.team_name)
        effective_location = fields.get("location", show.location)
        conflict = await session.scalar(select(Show).where(
            Show.id != show_id, Show.is_active == True,
            Show.show_date.between(effective_date - timedelta(hours=3), effective_date + timedelta(hours=3)),
            or_(Show.team_name == effective_team, Show.location == effective_location),
        ).limit(1))
        if conflict:
            raise web.HTTPConflict(text=json.dumps({"error": "scheduling_conflict", "field": "showDateLocal", "message": f"Конфликт с афишей «{conflict.title}»: та же команда или площадка в пределах трёх часов"}), content_type="application/json")
        updated = await crud.update_show(session, show_id, **fields)
        users = await crud.get_registered_users_for_show(session, show_id) if notify else []
    sent = failed = 0
    if notify and updated:
        text = f"✏️ Обновилась афиша <b>{h(updated.title)}</b>\n📅 {format_local(updated.show_date)}\n📍 {h(updated.location)}, {h(updated.city)}"
        bot = request.app[PUBLIC_BOT_KEY]
        for user in users:
            try:
                await send_with_retry(bot.send_message, user.telegram_id, text)
                sent += 1
            except Exception:
                failed += 1
    return web.json_response({"id": show_id, "notified": sent, "failed": failed})
