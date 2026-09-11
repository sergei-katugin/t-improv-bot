from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _manageable_api_show, _show_id
from admin_bot.registration_notifications import notify_manual_registration
from admin_bot.telegram_usernames import normalize_telegram_username


async def miniapp_attendees(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        offset = max(0, int(request.query.get("offset", "0")))
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_offset"}), content_type="application/json")
    # The endpoint returns two independently ordered collections. Keeping each
    # slice at half the response limit bounds a page to at most 100 attendees.
    limit = 50
    reg_after = manual_after = 0
    cursor = request.query.get("cursor")
    if cursor:
        try:
            reg_after, manual_after = (int(value) for value in cursor.split(":", 1))
            if reg_after < -1 or manual_after < -1:
                raise ValueError
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_cursor"}), content_type="application/json",
            )
    search = request.query.get("search", "").strip()[:100]
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        registrations_query = (
            select(Registration)
            .join(User, User.id == Registration.user_id)
            .options(selectinload(Registration.user))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
            .order_by(Registration.id)
            .limit(limit + 1)
        )
        manual_query = (
            select(ManualAttendee)
            .where(ManualAttendee.show_id == show_id)
            .order_by(ManualAttendee.id)
            .limit(limit + 1)
        )
        if cursor:
            registrations_query = registrations_query.where(
                Registration.id > reg_after if reg_after >= 0 else Registration.id < 0,
            )
            manual_query = manual_query.where(
                ManualAttendee.id > manual_after if manual_after >= 0 else ManualAttendee.id < 0,
            )
        elif offset:
            registrations_query = registrations_query.offset(offset)
            manual_query = manual_query.offset(offset)
        if search:
            pattern = f"%{search}%"
            registrations_query = registrations_query.where(or_(
                Registration.attendee_name.ilike(pattern), User.username.ilike(pattern),
            ))
            manual_query = manual_query.where(or_(
                ManualAttendee.name.ilike(pattern), ManualAttendee.contact.ilike(pattern),
            ))
        registrations = list((await session.execute(registrations_query)).scalars().all())
        manual = list((await session.execute(manual_query)).scalars().all())
        waitlist = []
        if not cursor and offset == 0:
            waitlist = list((await session.execute(
                select(WaitlistEntry).options(selectinload(WaitlistEntry.user)).where(
                    WaitlistEntry.show_id == show_id,
                    WaitlistEntry.promoted_at.is_(None),
                    WaitlistEntry.cancelled_at.is_(None),
                ).order_by(WaitlistEntry.created_at, WaitlistEntry.id).limit(100)
            )).scalars().all())
        occupied = await crud.count_active_registrations(session, show_id)
        arrived = int(await session.scalar(
            select(func.coalesce(func.sum(Registration.checked_in_count), 0))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
        ) or 0) + int(await session.scalar(
            select(func.coalesce(func.sum(ManualAttendee.checked_in_count), 0))
            .where(ManualAttendee.show_id == show_id)
        ) or 0)
        has_more = len(registrations) > limit or len(manual) > limit
        reg_page = registrations[:limit]
        manual_page = manual[:limit]
        next_cursor = None
        if has_more:
            next_reg = reg_page[-1].id if len(registrations) > limit else -1
            next_manual = manual_page[-1].id if len(manual) > limit else -1
            next_cursor = f"{next_reg}:{next_manual}"
        return web.json_response({
            "occupied": occupied, "maxSeats": show.max_seats, "arrived": arrived,
            "hasMore": has_more, "nextOffset": offset + limit,
            "nextCursor": next_cursor,
            "registrations": [{
                "id": item.id, "name": item.attendee_name, "guests": item.guests or 0,
                "username": item.user.username, "confirmed": item.confirmed,
                "checkedInCount": item.checked_in_count or 0, "source": item.source,
            } for item in reg_page],
            "manual": [{
                "id": item.id, "name": item.name, "contact": item.contact,
                "guests": item.guests or 0, "checkedInCount": item.checked_in_count or 0, "source": item.source,
            } for item in manual_page],
            "waitlist": [{"id": item.id, "name": item.attendee_name, "username": item.user.username, "position": index + 1} for index, item in enumerate(waitlist)],
        })


async def miniapp_add_manual_attendee(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if set(data) != {"name", "source", "contact", "guests"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    name = data["name"].strip() if isinstance(data["name"], str) else ""
    source_value = data["source"]
    source = source_value if isinstance(source_value, str) and source_value in {"telegram", "instagram", "other"} else None
    contact = data["contact"].strip() if isinstance(data["contact"], str) else ""
    guests = data["guests"]
    if not 2 <= len(name) <= 100:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "name"}), content_type="application/json")
    if source is None or not 2 <= len(contact) <= 256:
        field = "source" if source is None else "contact"
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": field}), content_type="application/json")
    if isinstance(guests, bool) or not isinstance(guests, int) or not 0 <= guests <= 6:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "guests"}), content_type="application/json")

    telegram_username = normalize_telegram_username(contact) if source == "telegram" else None
    if source == "telegram" and telegram_username is None:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "contact"}), content_type="application/json")
    normalized_contact = (
        f"Telegram: @{telegram_username}" if source == "telegram" else
        f"Instagram: @{contact.lstrip('@').strip()}" if source == "instagram" else
        f"Другое: {contact}"
    )
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if guests > show.max_guests:
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "guests"}), content_type="application/json")
        telegram_user = await crud.get_user_by_username(session, telegram_username) if telegram_username else None
        if telegram_user:
            attendee = await crud.register_user_safe(
                session, show_id, telegram_user.id, name, guests, source="miniapp_manual",
            )
            kind = "registration"
        else:
            count = await crud.add_manual_attendees(
                session, show_id, [name], source=source,
                contacts=[normalized_contact], guests=[guests],
            )
            attendee = count and True
            kind = "manual"
        if not attendee:
            raise web.HTTPConflict(text=json.dumps({"error": "capacity_exceeded"}), content_type="application/json")
        occupied = await crud.count_active_registrations(session, show_id)
        await notify_manual_registration(
            request.app[ADMIN_BOT_KEY], show, name=name, contact=normalized_contact,
            guests=guests, occupied=occupied, automatic=telegram_user is not None,
        )
        return web.json_response({"kind": kind, "occupied": occupied}, status=201)


async def miniapp_update_registration(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        registration_id = int(request.match_info["registration_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    if len(data) != 1 or not set(data).issubset({"guests", "checkedInCount"}):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        registration = await session.scalar(select(Registration).where(
            Registration.id == registration_id, Registration.show_id == show_id,
            Registration.is_cancelled == False,
        ))
        if registration is None:
            raise web.HTTPNotFound()
        if "guests" in data:
            guests = data["guests"]
            if isinstance(guests, bool) or not isinstance(guests, int) or not 0 <= guests <= 6:
                raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "guests"}), content_type="application/json")
            updated = await crud.update_registration_guests_safe(
                session, show_id, registration.user_id, guests,
            )
        else:
            count = data["checkedInCount"]
            if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 51:
                raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "checkedInCount"}), content_type="application/json")
            updated = await crud.set_registration_checkin_count(session, show_id, registration_id, count)
        if updated is None:
            raise web.HTTPConflict(text=json.dumps({"error": "update_rejected"}), content_type="application/json")
        return web.json_response({"id": updated.id})


async def miniapp_cancel_registration(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        registration_id = int(request.match_info["registration_id"])
    except ValueError:
        raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        registration = await session.scalar(select(Registration).where(
            Registration.id == registration_id, Registration.show_id == show_id,
            Registration.is_cancelled == False,
        ))
        if registration is None:
            raise web.HTTPNotFound()
        await crud.cancel_registration(session, show_id, registration.user_id)
        promoted = await crud.promote_waitlist(session, show_id)
        if promoted:
            promoted_registration, promoted_user = promoted
            show = await crud.get_show(session, show_id)
            try:
                await request.app[PUBLIC_BOT_KEY].send_message(
                    promoted_user.telegram_id,
                    f"🎉 Освободилось место! Ты автоматически записан(а) на <b>{h(show.title)}</b>.\n📅 {format_local(show.show_date)}",
                )
            except Exception:
                logger.exception("failed to notify promoted waitlist user show_id=%s user_id=%s", show_id, promoted_user.id)
        return web.json_response({"id": registration_id})
