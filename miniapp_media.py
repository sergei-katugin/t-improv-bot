from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _manageable_api_show, _record_audit, _require_admin, _show_id


POSTER_MAX_SIDE = 1600
POSTER_JPEG_QUALITY = 84


class InvalidPosterError(ValueError):
    pass


def _optimized_poster_bytes(content: bytes) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > MAX_POSTER_PIXELS:
                raise InvalidPosterError
            source.verify()
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source)
            image.thumbnail((POSTER_MAX_SIDE, POSTER_MAX_SIDE), Image.Resampling.LANCZOS)
            if image.mode in {"RGBA", "LA"}:
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=POSTER_JPEG_QUALITY, optimize=True)
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise InvalidPosterError from exc


async def miniapp_upload_poster(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        creator = await session.get(User, request["miniapp_user_id"])
        if creator is None:
            raise web.HTTPUnauthorized()
        creator_telegram_id = creator.telegram_id
    reader = await request.multipart()
    part = await reader.next()
    content_type = part.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() if part else ""
    if part is None or part.name != "poster" or content_type not in {
        "image/jpeg", "image/jpg", "image/png", "image/webp", "application/octet-stream", "",
    }:
        logger.warning("Poster upload rejected: unsupported content_type=%s", content_type or "missing")
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "unsupported_poster_type"}), content_type="application/json",
        )
    content = bytearray()
    while chunk := await part.read_chunk(size=64 * 1024):
        content.extend(chunk)
        if len(content) > MAX_POSTER_BYTES:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_POSTER_BYTES, actual_size=len(content))
    if not content:
        raise web.HTTPBadRequest(text=json.dumps({"error": "empty_poster"}), content_type="application/json")
    try:
        optimized = _optimized_poster_bytes(bytes(content))
    except InvalidPosterError:
        logger.warning("Poster upload rejected: invalid image content_type=%s size=%s", content_type or "missing", len(content))
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_poster"}), content_type="application/json",
        )
    bot = request.app[ADMIN_BOT_KEY]
    message = await bot.send_photo(
        creator_telegram_id,
        BufferedInputFile(optimized, filename="poster.jpg"),
    )
    file_id = message.photo[-1].file_id
    try:
        await bot.delete_message(creator_telegram_id, message.message_id)
    except Exception:
        pass
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        await crud.update_show(
            session, show.id, poster_file_id=file_id, pub_poster_file_id=None,
        )
    return web.json_response({"hasPoster": True})


async def miniapp_poster(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if not show.poster_file_id:
            raise web.HTTPNotFound()
        bot = request.app[ADMIN_BOT_KEY]
        telegram_file = await bot.get_file(show.poster_file_id)
        destination = io.BytesIO()
        await bot.download_file(telegram_file.file_path, destination=destination)
        content_type = mimetypes.guess_type(telegram_file.file_path or "poster.jpg")[0] or "application/octet-stream"
        return web.Response(
            body=destination.getvalue(), content_type=content_type,
            headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"},
        )


async def miniapp_options(request: web.Request) -> web.Response:
    async with AsyncSessionLocal() as session:
        teams = await crud.list_teams(
            session, None if request["miniapp_is_admin"] else request["miniapp_user_id"],
        )
        venues = await crud.list_venues(session)
        channels = await crud.list_ad_channels(session) if request["miniapp_is_admin"] else []
        return web.json_response({
            "teams": [{"id": team.id, "name": team.name, "members": team.members} for team in teams],
            "venues": [{
                "id": venue.id,
                "name": venue.name,
                "city": venue.city,
                "mapsUrl": venue.maps_url,
                "defaultSeats": venue.default_seats,
            } for venue in venues],
            "adChannels": [{
                "id": channel.id, "username": channel.username, "isActive": channel.is_active,
            } for channel in channels],
        })


async def miniapp_access_users(request: web.Request) -> web.Response:
    _require_admin(request)
    async with AsyncSessionLocal() as session:
        users = list((await session.scalars(
            select(User)
            .where(User.role.in_([UserRole.organizer, UserRole.admin]))
            .order_by(case((User.role == UserRole.admin, 0), else_=1), User.id)
            .limit(200)
        )).all())
    return web.json_response({
        "items": [{
            "id": user.id, "telegramId": user.telegram_id, "username": user.username,
            "firstName": user.first_name, "lastName": user.last_name,
            "role": user.role.value,
            "isCurrent": user.id == request["miniapp_user_id"],
            "isProtected": user.role == UserRole.admin or user.telegram_id in ADMIN_ID_LIST,
        } for user in users],
        "limit": 200,
    })


async def miniapp_create_access_invite(request: web.Request) -> web.Response:
    _require_admin(request)
    data = await _json_body(request)
    if data not in ({}, {"role": "organizer"}):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        invite = await crud.create_invite_token(session, UserRole.organizer)
    await _record_audit(request, "access.invite_created", "invite", invite.id, {"role": "organizer"})
    return web.json_response({
        "id": invite.id,
        "url": f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=inv_{invite.token}",
        "role": invite.role.value,
        "expiresAt": invite.expires_at.isoformat() if invite.expires_at else None,
        "ttlHours": settings.INVITE_TTL_HOURS,
    }, status=201)


async def miniapp_update_access_user(request: web.Request) -> web.Response:
    _require_admin(request)
    try:
        target_id = int(request.match_info["user_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    if set(data) != {"role"} or data["role"] not in {"organizer", "user"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_role"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        target = await session.get(User, target_id)
        if target is None:
            raise web.HTTPNotFound()
        if target.id == request["miniapp_user_id"]:
            raise web.HTTPConflict(text=json.dumps({"error": "cannot_change_self"}), content_type="application/json")
        if target.role == UserRole.admin or target.telegram_id in ADMIN_ID_LIST:
            raise web.HTTPConflict(text=json.dumps({"error": "protected_admin"}), content_type="application/json")
        target.role = UserRole(data["role"])
        await session.commit()
        target_role = target.role.value
        target_telegram_id = target.telegram_id
    await _record_audit(
        request, "access.role_changed", "user", target_id,
        {"role": target_role, "telegramId": target_telegram_id},
    )
    return web.json_response({"id": target_id, "role": target_role})
