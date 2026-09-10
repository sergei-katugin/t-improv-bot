from __future__ import annotations
from miniapp_common import *

def _show_payload(show: Show, occupied: int, has_published: bool | None = None) -> dict[str, object]:
    registrar_username = show.registrar.username if show.registrar else show.registrar_username
    payload: dict[str, object] = {
        "id": show.id,
        "title": show.title,
        "teamName": show.team_name,
        "showDate": show.show_date.isoformat(),
        "showDateLocal": utc_to_local(show.show_date).strftime("%Y-%m-%dT%H:%M"),
        "showDateLabel": format_local(show.show_date),
        "location": show.location,
        "city": show.city,
        "isPast": show.show_date < utc_now(),
        "isActive": show.is_active,
        "checkinEnabled": show.checkin_enabled,
        "maxSeats": show.max_seats,
        "maxGuests": show.max_guests,
        "registrationClosesAt": utc_to_local(show.registration_closes_at).strftime("%Y-%m-%dT%H:%M") if show.registration_closes_at else None,
        "registrationClosed": bool(show.registration_closes_at and show.registration_closes_at <= utc_now()),
        "occupiedSeats": occupied,
        "registrarUsername": registrar_username,
        "registrationUrl": _registration_url(show.id),
        "registrationChatId": show.registration_chat_id,
        "registrationChatTitle": show.registration_chat_title,
        "registrationChatNameMode": show.registration_chat_name_mode,
    }
    if has_published is not None:
        payload["hasPublished"] = has_published
    return payload


async def _record_audit(
    request: web.Request, action: str, entity_type: str, entity_id: int | None,
    details: dict[str, object] | None = None,
) -> None:
    """Record sanitized metadata; audit failures must not replay external actions."""
    try:
        serialized = json.dumps(details, ensure_ascii=False, separators=(",", ":")) if details else None
        if serialized and len(serialized) > 4000:
            serialized = json.dumps({"truncated": True}, separators=(",", ":"))
        async with AsyncSessionLocal() as session:
            session.add(AuditLog(
                actor_user_id=request["miniapp_user_id"], action=action,
                entity_type=entity_type, entity_id=entity_id, details=serialized,
            ))
            await session.commit()
    except Exception:
        logger.exception("Could not write audit action=%s entity=%s:%s", action, entity_type, entity_id)


def _audit_details(value: str | None) -> dict[str, object] | None:
    if not value:
        return None
    try:
        details = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Ignoring malformed audit details")
        return {"unavailable": True}
    return details if isinstance(details, dict) else {"unavailable": True}


def _occupied_expression():
    return func.coalesce(func.sum(case(
        (Registration.is_cancelled == False, 1 + Registration.guests),
        else_=0,
    )), 0)


def _registration_url(show_id: int) -> str:
    return f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=show_{show_id}"


def _require_admin(request: web.Request) -> None:
    if not request["miniapp_is_admin"]:
        raise web.HTTPForbidden(
            text=json.dumps({"error": "admin_access_required"}),
            content_type="application/json",
        )


def _required_text(data: dict, key: str, max_length: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > max_length:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_field", "field": key}),
            content_type="application/json",
        )
    return value.strip()


def _optional_text(data: dict, key: str, max_length: int) -> str | None:
    value = data.get(key)
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value.strip()) > max_length:
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_field", "field": key}),
            content_type="application/json",
        )
    return value.strip() or None


def _show_fields(data: dict, *, require_all: bool) -> dict[str, object]:
    allowed = {
        "title", "teamName", "showDateLocal", "location", "locationUrl", "city",
        "posterText", "maxSeats", "maxGuests", "registrationClosesAt", "registrarUsername", "checkinEnabled", "feedbackEnabled",
    }
    if not isinstance(data, dict) or any(key not in allowed for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    required = {"title", "teamName", "showDateLocal", "location", "city", "maxSeats"}
    if require_all and not required.issubset(data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "missing_fields"}), content_type="application/json")

    result: dict[str, object] = {}
    text_fields = {
        "title": ("title", 256), "teamName": ("team_name", 256),
        "location": ("location", 512), "city": ("city", 128),
    }
    for source, (target, limit) in text_fields.items():
        if source in data:
            result[target] = _required_text(data, source, limit)
    optional_fields = {
        "locationUrl": ("location_url", 512), "posterText": ("poster_text", 1800),
    }
    for source, (target, limit) in optional_fields.items():
        if source in data:
            result[target] = _optional_text(data, source, limit)
    if result.get("location_url"):
        parsed = urlparse(str(result["location_url"]))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_field", "field": "locationUrl"}),
                content_type="application/json",
            )
    if "showDateLocal" in data:
        try:
            local_date = datetime.fromisoformat(str(data["showDateLocal"]))
        except ValueError as exc:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_field", "field": "showDateLocal"}),
                content_type="application/json",
            ) from exc
        show_date = local_naive_to_utc(local_date)
        if show_date <= utc_now():
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "show_date_in_past", "field": "showDateLocal"}),
                content_type="application/json",
            )
        result["show_date"] = show_date
    if "maxSeats" in data:
        seats = data["maxSeats"]
        if isinstance(seats, bool) or not isinstance(seats, int) or not 1 <= seats <= 10_000:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_field", "field": "maxSeats"}),
                content_type="application/json",
            )
        result["max_seats"] = seats
    if "maxGuests" in data:
        guests = data["maxGuests"]
        if isinstance(guests, bool) or not isinstance(guests, int) or not 0 <= guests <= 6:
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "maxGuests"}), content_type="application/json")
        result["max_guests"] = guests
    elif require_all:
        result["max_guests"] = 6
    if "registrationClosesAt" in data:
        raw_close = data["registrationClosesAt"]
        if raw_close in (None, ""):
            result["registration_closes_at"] = None
        else:
            try:
                close_at = local_naive_to_utc(datetime.fromisoformat(str(raw_close)))
            except ValueError as exc:
                raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "registrationClosesAt"}), content_type="application/json") from exc
            result["registration_closes_at"] = close_at
    if result.get("registration_closes_at") and result.get("show_date") and result["registration_closes_at"] >= result["show_date"]:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "registrationClosesAt"}), content_type="application/json")
    if require_all and "registrationClosesAt" not in data:
        result["registration_closes_at"] = result["show_date"] - timedelta(hours=1)
    if "registrarUsername" in data:
        raw_username = _optional_text(data, "registrarUsername", 64)
        username = normalize_telegram_username(raw_username)
        if raw_username and username is None:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "invalid_field", "field": "registrarUsername"}),
                content_type="application/json",
            )
        result["registrar_username"] = username
    for source, target in (("checkinEnabled", "checkin_enabled"), ("feedbackEnabled", "feedback_enabled")):
        if source in data:
            if not isinstance(data[source], bool):
                raise web.HTTPBadRequest(
                    text=json.dumps({"error": "invalid_field", "field": source}),
                    content_type="application/json",
                )
            result[target] = data[source]
    return result


async def _json_body(request: web.Request) -> dict:
    if request.content_length is not None and request.content_length > 32_768:
        raise web.HTTPRequestEntityTooLarge(max_size=32_768, actual_size=request.content_length)
    try:
        data = await request.json()
    except (json.JSONDecodeError, ValueError):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_json"}), content_type="application/json")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    return data


async def _manageable_api_show(session, request: web.Request, show_id: int) -> Show:
    db_user = await session.get(User, request["miniapp_user_id"])
    show = await crud.get_show(session, show_id)
    if show is None or not can_manage_owned(show.creator_id, db_user, request["miniapp_is_admin"]):
        raise web.HTTPNotFound()
    return show


def _show_id(request: web.Request) -> int:
    try:
        return int(request.match_info["show_id"])
    except (KeyError, ValueError):
        raise web.HTTPNotFound()
