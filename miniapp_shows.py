from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _occupied_expression, _show_payload


async def miniapp_shows(request: web.Request) -> web.Response:
    status = request.query.get("status", "upcoming")
    if status not in {"upcoming", "past", "all"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_status"}), content_type="application/json")
    try:
        offset = max(0, int(request.query.get("offset", "0")))
        year = int(request.query["year"]) if request.query.get("year") else None
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_filter"}), content_type="application/json")
    if year is not None and not 2000 <= year <= 2100:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_filter"}), content_type="application/json")
    team = request.query.get("team", "").strip()[:256]
    cursor_date = None
    cursor_id = None
    cursor = request.query.get("cursor")
    if cursor:
        try:
            raw_date, raw_id = cursor.rsplit("|", 1)
            cursor_date, cursor_id = datetime.fromisoformat(raw_date), int(raw_id)
        except (ValueError, TypeError):
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_cursor"}), content_type="application/json",
            )
    manual_occupied = (
        select(func.coalesce(func.sum(ManualAttendee.guests + 1), 0))
        .where(ManualAttendee.show_id == Show.id)
        .correlate(Show)
        .scalar_subquery()
    )
    occupied = (_occupied_expression() + manual_occupied).label("occupied")
    has_published = exists(select(AnnouncementLog.id).where(AnnouncementLog.show_id == Show.id)).label("has_published")
    query = (
        select(Show, occupied, has_published)
        .options(selectinload(Show.registrar))
        .outerjoin(Registration, Registration.show_id == Show.id)
        .group_by(Show.id)
        .order_by(Show.show_date.desc(), Show.id.desc())
        .limit(MAX_SHOWS_PER_PAGE + 1)
    )
    if cursor_date is not None and cursor_id is not None:
        query = query.where(or_(
            Show.show_date < cursor_date,
            and_(Show.show_date == cursor_date, Show.id < cursor_id),
        ))
    elif offset:
        query = query.offset(offset)
    if not request["miniapp_is_admin"]:
        query = query.where(Show.creator_id == request["miniapp_user_id"])
    if status == "upcoming":
        query = query.where(Show.show_date >= utc_now(), Show.is_active == True)
    elif status == "past":
        query = query.where(Show.show_date < utc_now())
    if team:
        query = query.where(Show.team_name == team)
    if year is not None:
        query = query.where(
            Show.show_date >= local_naive_to_utc(datetime(year, 1, 1)),
            Show.show_date < local_naive_to_utc(datetime(year + 1, 1, 1)),
        )

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query)).all()
        items = rows[:MAX_SHOWS_PER_PAGE]
        next_cursor = None
        if len(rows) > MAX_SHOWS_PER_PAGE and items:
            last_show = items[-1][0]
            next_cursor = f"{last_show.show_date.isoformat()}|{last_show.id}"
        return web.json_response({
            "items": [_show_payload(show, int(count), bool(published)) for show, count, published in items],
            "limit": MAX_SHOWS_PER_PAGE,
            "hasMore": len(rows) > MAX_SHOWS_PER_PAGE,
            "nextOffset": offset + len(items),
            "nextCursor": next_cursor,
        })


async def miniapp_show_detail(request: web.Request) -> web.Response:
    try:
        show_id = int(request.match_info["show_id"])
    except ValueError:
        raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        show = await session.scalar(
            select(Show).options(selectinload(Show.registrar)).where(Show.id == show_id)
        )
        if show is None or not can_manage_owned(
            show.creator_id,
            await session.get(User, request["miniapp_user_id"]),
            request["miniapp_is_admin"],
        ):
            raise web.HTTPNotFound()
        occupied = await crud.count_active_registrations(session, show.id)
        payload = _show_payload(show, int(occupied or 0))
        payload.update({
            "posterText": show.poster_text,
            "posterTextNewcomer": show.poster_text_newcomer,
            "locationUrl": show.location_url,
            "feedbackEnabled": show.feedback_enabled,
            "checkinEnabled": show.checkin_enabled,
            "hasPoster": bool(show.poster_file_id),
            "hasPublished": await crud.has_any_announcement_been_sent(session, show.id),
        })
        return web.json_response(payload)


async def miniapp_attention(request: web.Request) -> web.Response:
    manual_occupied = (
        select(func.coalesce(func.sum(ManualAttendee.guests + 1), 0))
        .where(ManualAttendee.show_id == Show.id)
        .correlate(Show).scalar_subquery()
    )
    registered_occupied = (
        select(func.coalesce(func.sum(Registration.guests + 1), 0))
        .where(Registration.show_id == Show.id, Registration.is_cancelled == False)
        .correlate(Show).scalar_subquery()
    )
    announced = exists(
        select(AnnouncementLog.id).where(AnnouncementLog.show_id == Show.id)
    ).label("announced")
    query = (
        select(Show, (registered_occupied + manual_occupied).label("occupied"), announced)
        .where(Show.is_active == True, Show.show_date >= utc_now())
        .order_by(Show.show_date).limit(20)
    )
    if not request["miniapp_is_admin"]:
        query = query.where(Show.creator_id == request["miniapp_user_id"])
    async with AsyncSessionLocal() as session:
        shows = (await session.execute(query)).all()
        items = []
        for show, occupied, announced in shows:
            if not announced:
                items.append({"showId": show.id, "showTitle": show.title, "kind": "announcement", "label": "Опубликовать анонс"})
            elif show.show_date <= utc_now() + timedelta(days=7) and occupied < show.max_seats * .5:
                items.append({"showId": show.id, "showTitle": show.title, "kind": "announcement", "label": "Низкая заполненность — повторить анонс"})
            if not show.registration_chat_id:
                items.append({"showId": show.id, "showTitle": show.title, "kind": "chat", "label": "Подключить чат записей"})
            if not show.registrar_id and not show.registrar_username:
                items.append({"showId": show.id, "showTitle": show.title, "kind": "edit", "label": "Указать ответственного"})
        return web.json_response({"items": items[:12]})
