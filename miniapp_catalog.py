from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _optional_text, _require_admin, _required_text


async def miniapp_create_team(request: web.Request) -> web.Response:
    data = await _json_body(request)
    if any(key not in {"name", "members"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    name = _required_text(data, "name", 256)
    raw_members = _optional_text(data, "members", 2000)
    members = normalize_telegram_username_list(raw_members)
    if members is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_field", "field": "members"}),
            content_type="application/json",
        )
    async with AsyncSessionLocal() as session:
        team = await crud.create_team(
            session, name=name, members=serialize_telegram_usernames(members),
            creator_id=request["miniapp_user_id"],
        )
        return web.json_response({"id": team.id}, status=201)


async def miniapp_update_team(request: web.Request) -> web.Response:
    try:
        team_id = int(request.match_info["team_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    if not data or any(key not in {"name", "members"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        team = await crud.get_team(session, team_id)
        if team is None or not can_manage_owned(
            team.creator_id, await session.get(User, request["miniapp_user_id"]), request["miniapp_is_admin"],
        ):
            raise web.HTTPNotFound()
        fields: dict[str, object] = {}
        if "name" in data:
            fields["name"] = _required_text(data, "name", 256)
        if "members" in data:
            raw_members = _optional_text(data, "members", 2000)
            members = normalize_telegram_username_list(raw_members)
            if members is None:
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "invalid_field", "field": "members"}),
                    content_type="application/json",
                )
            fields["members"] = serialize_telegram_usernames(members)
        await crud.update_team(session, team_id, **fields)
        return web.json_response({"id": team_id})


async def miniapp_delete_team(request: web.Request) -> web.Response:
    try:
        team_id = int(request.match_info["team_id"])
    except ValueError:
        raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        team = await crud.get_team(session, team_id)
        if team is None or not can_manage_owned(
            team.creator_id, await session.get(User, request["miniapp_user_id"]), request["miniapp_is_admin"],
        ):
            raise web.HTTPNotFound()
        await crud.delete_team(session, team_id)
    return web.json_response({"id": team_id})


async def miniapp_create_venue(request: web.Request) -> web.Response:
    _require_admin(request)
    data = await _json_body(request)
    if any(key not in {"name", "city", "mapsUrl", "defaultSeats"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    name = _required_text(data, "name", 256)
    city = _required_text(data, "city", 128)
    maps_url = _optional_text(data, "mapsUrl", 512)
    if maps_url:
        parsed = urlparse(maps_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_field", "field": "mapsUrl"}),
                content_type="application/json",
            )
    seats = data.get("defaultSeats")
    if isinstance(seats, bool) or not isinstance(seats, int) or not 1 <= seats <= 10_000:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_field", "field": "defaultSeats"}),
            content_type="application/json",
        )
    async with AsyncSessionLocal() as session:
        venue = await crud.create_venue(session, name, city, maps_url, seats)
        return web.json_response({"id": venue.id}, status=201)


async def miniapp_update_venue(request: web.Request) -> web.Response:
    _require_admin(request)
    try:
        venue_id = int(request.match_info["venue_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    if not data or any(key not in {"name", "city", "mapsUrl", "defaultSeats"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    fields: dict[str, object] = {}
    if "name" in data: fields["name"] = _required_text(data, "name", 256)
    if "city" in data: fields["city"] = _required_text(data, "city", 128)
    if "mapsUrl" in data:
        maps_url = _optional_text(data, "mapsUrl", 512)
        if maps_url and (urlparse(maps_url).scheme not in {"http", "https"} or not urlparse(maps_url).netloc):
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "mapsUrl"}), content_type="application/json")
        fields["maps_url"] = maps_url
    if "defaultSeats" in data:
        seats = data["defaultSeats"]
        if isinstance(seats, bool) or not isinstance(seats, int) or not 1 <= seats <= 10_000:
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "defaultSeats"}), content_type="application/json")
        fields["default_seats"] = seats
    async with AsyncSessionLocal() as session:
        venue = await crud.update_venue(session, venue_id, **fields)
        if venue is None: raise web.HTTPNotFound()
    return web.json_response({"id": venue_id})


async def miniapp_delete_venue(request: web.Request) -> web.Response:
    _require_admin(request)
    try: venue_id = int(request.match_info["venue_id"])
    except ValueError: raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        if await crud.get_venue(session, venue_id) is None: raise web.HTTPNotFound()
        await crud.delete_venue(session, venue_id)
    return web.json_response({"id": venue_id})


async def miniapp_create_ad_channel(request: web.Request) -> web.Response:
    _require_admin(request)
    data = await _json_body(request)
    if set(data) != {"username"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    username = normalize_telegram_username(_required_text(data, "username", 64))
    if username is None:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_field", "field": "username"}),
            content_type="application/json",
        )
    async with AsyncSessionLocal() as session:
        channel = await crud.add_ad_channel(session, username)
        if channel is None:
            raise web.HTTPConflict(
                text=json.dumps({"error": "channel_exists"}), content_type="application/json",
            )
        return web.json_response({"id": channel.id}, status=201)


async def miniapp_toggle_ad_channel(request: web.Request) -> web.Response:
    _require_admin(request)
    try:
        channel_id = int(request.match_info["channel_id"])
    except ValueError:
        raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        channel = await crud.toggle_ad_channel(session, channel_id)
        if channel is None:
            raise web.HTTPNotFound()
        return web.json_response({"id": channel.id, "isActive": channel.is_active})


async def miniapp_delete_ad_channel(request: web.Request) -> web.Response:
    _require_admin(request)
    try: channel_id = int(request.match_info["channel_id"])
    except ValueError: raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        if not await crud.delete_ad_channel(session, channel_id): raise web.HTTPNotFound()
    return web.json_response({"id": channel_id})
