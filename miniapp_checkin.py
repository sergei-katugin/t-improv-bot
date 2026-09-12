from miniapp_common import *
from miniapp_helpers import _json_body, _manageable_api_show, _show_id
from db.models import ShowCheckinStaff
from checkin_service import arrival_stats, notify_arrivals


async def accessible_checkin_show(session, request):
    show_id = _show_id(request)
    user = await session.get(User, request["miniapp_user_id"])
    show = await session.scalar(select(Show).where(Show.id == show_id).with_for_update())
    if show is None or not show.is_active or not show.checkin_enabled:
        raise web.HTTPNotFound()
    if not can_manage_owned(show.creator_id, user, request["miniapp_is_admin"]) and not await crud.has_checkin_access(session, show_id, user.id):
        raise web.HTTPNotFound()
    return show


async def miniapp_checkin_shows(request):
    async with AsyncSessionLocal() as session:
        items = list((await session.scalars(select(Show).join(ShowCheckinStaff).where(
            ShowCheckinStaff.user_id == request["miniapp_user_id"], ShowCheckinStaff.expires_at > utc_now(),
            Show.is_active == True, Show.checkin_enabled == True,
        ).order_by(Show.show_date).limit(100))).all())
        return web.json_response({"items": [{"id": show.id, "title": show.title, "date": format_local(show.show_date)} for show in items]})


async def miniapp_checkin(request):
    async with AsyncSessionLocal() as session:
        show = await accessible_checkin_show(session, request)
        stats = await arrival_stats(session, show)
        query = request.query.get("search", "").strip()[:100]
        items = []
        if show.checkin_mode == "named":
            regs = select(Registration).join(User).where(Registration.show_id == show.id, Registration.is_cancelled == False)
            manual = select(ManualAttendee).where(ManualAttendee.show_id == show.id)
            if query:
                regs = regs.where(or_(Registration.attendee_name.ilike(f"%{query}%"), User.username.ilike(f"%{query.lstrip('@')}%")))
                manual = manual.where(ManualAttendee.name.ilike(f"%{query}%"))
            for kind, statement in (("registration", regs), ("manual", manual)):
                for item in (await session.scalars(statement.order_by(Registration.id if kind == "registration" else ManualAttendee.id).limit(50))).all():
                    items.append({"kind": kind, "id": item.id, "name": item.attendee_name if kind == "registration" else item.name,
                                  "booked": 1 + (item.guests or 0), "arrived": item.checked_in_count or 0})
        return web.json_response({**stats, "id": show.id, "title": show.title, "mode": show.checkin_mode,
                                  "reportEvery": show.checkin_report_every, "items": items})


async def miniapp_checkin_update(request):
    data = await _json_body(request)
    async with AsyncSessionLocal() as session:
        show = await accessible_checkin_show(session, request)
        if show.checkin_mode == "counter":
            delta = data.get("delta")
            if type(delta) is not int or delta not in (-1, 1, 2, 3):
                raise web.HTTPBadRequest()
            if type(data.get("expected")) is not int or data["expected"] != (show.checkin_counter or 0):
                raise web.HTTPConflict(text="Счётчик уже изменён. Обнови данные и повтори отметку.")
            show.checkin_counter = max(0, (show.checkin_counter or 0) + delta)
            await session.commit()
        else:
            count, item_id, kind = data.get("count"), data.get("id"), data.get("kind")
            model = Registration if kind == "registration" else ManualAttendee if kind == "manual" else None
            if model is None or type(count) is not int or type(item_id) is not int:
                raise web.HTTPBadRequest()
            item = await session.scalar(select(model).where(model.id == item_id, model.show_id == show.id).with_for_update())
            if item is None or (kind == "registration" and item.is_cancelled):
                raise web.HTTPNotFound()
            if not 0 <= count <= 1 + (item.guests or 0):
                raise web.HTTPBadRequest()
            if type(data.get("arrived")) is not int or data["arrived"] != (item.checked_in_count or 0):
                raise web.HTTPConflict(text="Запись уже изменена другим сотрудником.")
            item.checked_in_count = count
            item.checked_in_at = utc_now() if count else None
            await session.commit()
        stats = await arrival_stats(session, show)
        await notify_arrivals(request.app[ADMIN_BOT_KEY], session, show, stats)
        return web.json_response(stats)


async def miniapp_checkin_config(request):
    data = await _json_body(request)
    mode, step = data.get("mode"), data.get("reportEvery")
    if mode not in ("named", "counter") or type(step) is not int or not 1 <= step <= 100:
        raise web.HTTPBadRequest()
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, _show_id(request))
        await session.refresh(show, with_for_update=True)
        stats = await arrival_stats(session, show)
        if stats["arrived"] and mode != show.checkin_mode:
            raise web.HTTPConflict(text="Нельзя менять режим после начала входа")
        await crud.update_show(session, show.id, checkin_mode=mode, checkin_report_every=step)
    return web.json_response({"ok": True})


async def miniapp_checkin_invite(request):
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, _show_id(request))
        if not show.checkin_enabled:
            raise web.HTTPBadRequest()
        invite = await crud.create_checkin_invite(session, show.id, settings.INVITE_TTL_HOURS)
    return web.json_response({"url": f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=door_{invite.token}", "ttlHours": settings.INVITE_TTL_HOURS})
