from __future__ import annotations

import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import mimetypes
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qsl
from urllib.parse import urlparse

from aiohttp import web
from aiogram import Bot
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, LinkPreviewOptions
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import selectinload

from admin_bot.security import can_manage_owned
from admin_bot.telegram_usernames import (
    normalize_telegram_username, normalize_telegram_username_list,
    serialize_telegram_usernames,
)
from config import ADMIN_ID_LIST, settings
from db import crud
from db.base import AsyncSessionLocal
from db.models import AuditLog, ManualAttendee, Registration, Show, ShowFeedback, User, UserRole
from html_utils import h
from telegram_delivery import send_with_retry
from time_utils import format_local, local_naive_to_utc, utc_now, utc_to_local


MINIAPP_DIST = Path(__file__).with_name("miniapp") / "dist"
ADMIN_BOT_KEY = web.AppKey("miniapp_admin_bot", Bot)
PUBLIC_BOT_KEY = web.AppKey("miniapp_public_bot", Bot)
MAX_INIT_DATA_AGE_SECONDS = 60 * 60
MAX_SHOWS_PER_PAGE = 100
logger = logging.getLogger(__name__)


class MiniAppAuthError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramMiniAppUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = MAX_INIT_DATA_AGE_SECONDS,
) -> TelegramMiniAppUser:
    """Validate Telegram Mini App initData according to Telegram's HMAC scheme."""
    if not init_data or len(init_data) > 8192:
        raise MiniAppAuthError("missing or oversized init data")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MiniAppAuthError("malformed init data") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise MiniAppAuthError("duplicate init data field")
        fields[key] = value

    supplied_hash = fields.pop("hash", "")
    if len(supplied_hash) != 64:
        raise MiniAppAuthError("invalid init data hash")
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_hash, expected_hash):
        raise MiniAppAuthError("invalid init data signature")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniAppAuthError("invalid auth date") from exc
    current_time = int(time.time()) if now is None else now
    if auth_date > current_time + 30 or current_time - auth_date > max_age_seconds:
        raise MiniAppAuthError("expired init data")

    try:
        telegram_user = json.loads(fields["user"])
        if not isinstance(telegram_user, dict):
            raise TypeError
        telegram_id = int(telegram_user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MiniAppAuthError("invalid Telegram user") from exc
    if telegram_id <= 0:
        raise MiniAppAuthError("invalid Telegram user id")
    return TelegramMiniAppUser(
        telegram_id=telegram_id,
        username=telegram_user.get("username"),
        first_name=telegram_user.get("first_name"),
        last_name=telegram_user.get("last_name"),
    )


def _extract_init_data(request: web.Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("tma "):
        return authorization[4:]
    return request.headers.get("X-Telegram-Init-Data", "")


@web.middleware
async def miniapp_auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    init_data = _extract_init_data(request)
    try:
        telegram_user = validate_telegram_init_data(
            init_data, settings.ADMIN_BOT_TOKEN,
        )
    except MiniAppAuthError as exc:
        logger.warning(
            "Mini App authentication rejected request_id=%s path=%s reason=%s init_data_present=%s",
            request.get("miniapp_request_id", "unknown"), request.path, exc, bool(init_data),
        )
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "telegram_auth_failed"}),
            content_type="application/json",
        )

    async with AsyncSessionLocal() as session:
        db_user = await session.scalar(
            select(User).where(User.telegram_id == telegram_user.telegram_id)
        )
        if db_user is None or db_user.role not in (UserRole.organizer, UserRole.admin):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "organizer_access_required"}),
                content_type="application/json",
            )
        request["miniapp_user_id"] = db_user.id
        request["miniapp_telegram_id"] = telegram_user.telegram_id
        request["miniapp_is_admin"] = (
            db_user.role == UserRole.admin or telegram_user.telegram_id in ADMIN_ID_LIST
        )
    return await handler(request)


@web.middleware
async def miniapp_request_logging_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    request_id = secrets.token_hex(6)
    request["miniapp_request_id"] = request_id
    started_at = time.monotonic()
    status = 500
    try:
        response = await handler(request)
        status = response.status
        response.headers["X-Request-ID"] = request_id
        return response
    except web.HTTPException as exc:
        status = exc.status
        exc.headers["X-Request-ID"] = request_id
        raise
    except Exception:
        logger.exception(
            "Mini App request failed request_id=%s method=%s path=%s user_id=%s telegram_id=%s",
            request_id, request.method, request.path,
            request.get("miniapp_user_id"), request.get("miniapp_telegram_id"),
        )
        response = web.json_response(
            {"error": "internal_error", "requestId": request_id}, status=500,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = (time.monotonic() - started_at) * 1000
        log = logger.warning if status >= 400 else logger.info
        log(
            "Mini App request completed request_id=%s method=%s path=%s status=%s "
            "duration_ms=%.1f user_id=%s telegram_id=%s",
            request_id, request.method, request.path, status, duration_ms,
            request.get("miniapp_user_id"), request.get("miniapp_telegram_id"),
        )


@web.middleware
async def miniapp_security_headers_middleware(request: web.Request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as response:
        _set_miniapp_security_headers(request, response)
        raise
    _set_miniapp_security_headers(request, response)
    return response


def _set_miniapp_security_headers(request: web.Request, response: web.StreamResponse) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()",
    )
    if request.path.startswith("/api/miniapp/"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    elif request.path == "/app" or request.path.startswith("/app/"):
        if request.path.startswith("/app/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        else:
            response.headers.setdefault("Cache-Control", "no-store, max-age=0, must-revalidate")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Expires", "0")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
            "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org; "
            "base-uri 'none'; form-action 'self'",
        )


def _show_payload(show: Show, occupied: int) -> dict[str, object]:
    registrar_username = show.registrar.username if show.registrar else show.registrar_username
    return {
        "id": show.id,
        "title": show.title,
        "teamName": show.team_name,
        "showDate": show.show_date.isoformat(),
        "showDateLocal": utc_to_local(show.show_date).strftime("%Y-%m-%dT%H:%M"),
        "showDateLabel": format_local(show.show_date),
        "location": show.location,
        "city": show.city,
        "isActive": show.is_active,
        "checkinEnabled": show.checkin_enabled,
        "maxSeats": show.max_seats,
        "occupiedSeats": occupied,
        "registrarUsername": registrar_username,
        "registrationUrl": _registration_url(show.id),
        "registrationChatId": show.registration_chat_id,
        "registrationChatTitle": show.registration_chat_title,
        "registrationChatNameMode": show.registration_chat_name_mode,
    }


async def miniapp_me(request: web.Request) -> web.Response:
    async with AsyncSessionLocal() as session:
        user = await session.get(User, request["miniapp_user_id"])
        if user is None:
            raise web.HTTPUnauthorized()
        return web.json_response({
            "id": user.id,
            "telegramId": user.telegram_id,
            "username": user.username,
            "firstName": user.first_name,
            "lastName": user.last_name,
            "role": user.role.value,
        })


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


async def miniapp_audit_log(request: web.Request) -> web.Response:
    _require_admin(request)
    try:
        offset = max(0, int(request.query.get("offset", "0")))
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_offset"}), content_type="application/json")
    limit = 100
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(AuditLog, User)
            .outerjoin(User, User.id == AuditLog.actor_user_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset).limit(limit + 1)
        )).all()
    items = rows[:limit]
    return web.json_response({
        "items": [{
            "id": item.id, "action": item.action, "entityType": item.entity_type,
            "entityId": item.entity_id, "details": _audit_details(item.details),
            "createdAt": item.created_at.isoformat(),
            "actor": None if actor is None else {
                "id": actor.id, "username": actor.username, "firstName": actor.first_name,
                "lastName": actor.last_name, "telegramId": actor.telegram_id,
            },
        } for item, actor in items],
        "hasMore": len(rows) > limit, "nextOffset": offset + len(items),
    })


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
    occupied = _occupied_expression().label("occupied")
    query = (
        select(Show, occupied)
        .options(selectinload(Show.registrar))
        .outerjoin(Registration, Registration.show_id == Show.id)
        .group_by(Show.id)
        .order_by(Show.show_date.desc())
        .offset(offset).limit(MAX_SHOWS_PER_PAGE + 1)
    )
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
        return web.json_response({
            "items": [_show_payload(show, int(count)) for show, count in items],
            "limit": MAX_SHOWS_PER_PAGE,
            "hasMore": len(rows) > MAX_SHOWS_PER_PAGE,
            "nextOffset": offset + len(items),
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
        occupied = await session.scalar(
            select(_occupied_expression()).where(Registration.show_id == show.id)
        )
        payload = _show_payload(show, int(occupied or 0))
        payload.update({
            "posterText": show.poster_text,
            "locationUrl": show.location_url,
            "feedbackEnabled": show.feedback_enabled,
            "checkinEnabled": show.checkin_enabled,
            "hasPoster": bool(show.poster_file_id),
        })
        return web.json_response(payload)


async def miniapp_announcement_preview(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        occupied = await crud.count_active_registrations(session, show_id)
        from scheduler.jobs import build_announcement_text
        return web.json_response({
            "html": build_announcement_text(
                show, seats_left=max(0, show.max_seats - occupied),
            ),
            "hasPoster": bool(show.poster_file_id),
            "hasPublished": await crud.has_any_announcement_been_sent(session, show_id),
        })


async def miniapp_promotion(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        occupied = await crud.count_active_registrations(session, show_id)
        channels = await crud.get_active_ad_channels(session)
        from scheduler.jobs import build_announcement_text
        html = build_announcement_text(show, seats_left=max(0, show.max_seats - occupied))
        plain_text = re.sub(r"<[^>]+>", "", html)
        registration_url = (
            f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=show_{show.id}"
        )
        return web.json_response({
            "html": html,
            "text": f"{plain_text}\n\n📝 Записаться: {registration_url}",
            "registrationUrl": registration_url,
            "hasPoster": bool(show.poster_file_id),
            "hasPublished": await crud.has_any_announcement_been_sent(session, show_id),
            "channels": [
                {"id": channel.id, "username": channel.username, "url": channel.url}
                for channel in channels
            ],
        })


async def miniapp_publish(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if any(key not in {"repeat", "confirmed", "idempotencyKey"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    repeat = data.get("repeat") is True
    if repeat and data.get("confirmed") is not True:
        raise web.HTTPBadRequest(text=json.dumps({"error": "confirmation_required"}), content_type="application/json")
    idempotency_key = data.get("idempotencyKey")
    if repeat and (not isinstance(idempotency_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", idempotency_key)):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_idempotency_key"}), content_type="application/json")

    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        if not show.is_active:
            raise web.HTTPConflict(text=json.dumps({"error": "show_cancelled"}), content_type="application/json")
        missing = [name for value, name in (
            (show.poster_text, "posterText"), (show.poster_file_id, "poster"),
        ) if not value]
        if missing:
            raise web.HTTPConflict(
                text=json.dumps({"error": "announcement_incomplete", "fields": missing}),
                content_type="application/json",
            )
        if repeat:
            announcement_type = await crud.claim_repeat_announcement(session, show_id, idempotency_key)
            if announcement_type is None:
                raise web.HTTPConflict(text=json.dumps({"error": "already_processed"}), content_type="application/json")
        else:
            if not await crud.claim_manual_announcement(session, show_id):
                raise web.HTTPConflict(text=json.dumps({"error": "already_published"}), content_type="application/json")
            announcement_type = "manual"
        occupied = await crud.count_active_registrations(session, show_id)
        from scheduler.jobs import build_announcement_text
        text = build_announcement_text(show, seats_left=max(0, show.max_seats - occupied))

    try:
        from scheduler.jobs import send_to_channel
        message_id = await send_to_channel(
            request.app[PUBLIC_BOT_KEY], request.app[ADMIN_BOT_KEY], show, text,
        )
    except Exception:
        async with AsyncSessionLocal() as session:
            await crud.release_announcement_claim(session, show_id, announcement_type)
        raise
    async with AsyncSessionLocal() as session:
        await crud.save_channel_message_id(session, show_id, message_id, announcement_type)
    await _record_audit(
        request, "show.republished" if repeat else "show.published", "show", show_id,
        {"announcementType": announcement_type, "messageId": message_id},
    )
    return web.json_response({"messageId": message_id, "announcementType": announcement_type})


def _registration_url(show_id: int) -> str:
    return f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=show_{show_id}"


async def miniapp_show_qr(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
    import qrcode
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(_registration_url(show.id))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return web.Response(
        body=output.getvalue(), content_type="image/png",
        headers={
            "Cache-Control": "private, max-age=300",
            "Content-Disposition": f'attachment; filename="show-{show.id}-qr.png"',
            "X-Content-Type-Options": "nosniff",
        },
    )


async def miniapp_clone_show(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if set(data) != {"showDateLocal"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    raw_date = data.get("showDateLocal")
    try:
        show_date = local_naive_to_utc(datetime.fromisoformat(raw_date))
    except (TypeError, ValueError):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "showDateLocal"}), content_type="application/json")
    if show_date <= utc_now():
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "showDateLocal"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        source = await _manageable_api_show(session, request, show_id)
        clone = await crud.create_show(
            session,
            title=source.title, team_name=source.team_name, show_date=show_date,
            location=source.location, location_url=source.location_url, city=source.city,
            poster_text=source.poster_text, poster_file_id=source.poster_file_id,
            max_seats=source.max_seats, creator_id=request["miniapp_user_id"],
            registrar_id=source.registrar_id, registrar_username=source.registrar_username,
            checkin_enabled=source.checkin_enabled, feedback_enabled=source.feedback_enabled,
        )
        clone_id = clone.id
    await _record_audit(request, "show.cloned", "show", clone_id, {"sourceShowId": show_id})
    return web.json_response({"id": clone_id}, status=201)


async def miniapp_cancel_show(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if data != {"confirmed": True}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "confirmation_required"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        was_announced = await crud.has_any_announcement_been_sent(session, show_id)
        reply_to = await crud.get_last_channel_message_id(session, show_id)
        if not await crud.deactivate_show(session, show_id):
            raise web.HTTPConflict(text=json.dumps({"error": "already_cancelled"}), content_type="application/json")
    await _record_audit(request, "show.cancelled", "show", show_id)

    public_bot = request.app[PUBLIC_BOT_KEY]
    admin_bot = request.app[ADMIN_BOT_KEY]
    if was_announced:
        channel_text = (
            "🚫 <b>Шоу отменено</b>\n\n"
            f"🎭 <s>{h(show.title)}</s>\n"
            f"📅 <s>{h(format_local(show.show_date))}</s>\n"
            f"📍 <s>{h(show.location)}, {h(show.city)}</s>\n\n"
            "Приносим извинения за неудобства. Следите за новыми анонсами!"
        )
        try:
            from scheduler.jobs import send_to_channel
            await send_to_channel(
                public_bot, admin_bot, show, channel_text,
                with_button=False, reply_to_message_id=reply_to,
            )
        except Exception:
            logger.exception("Could not post Mini App cancellation to channel show_id=%s", show_id)

    personal_text = (
        "❌ <b>Шоу отменено</b>\n\n"
        "К сожалению, мероприятие, на которое ты записан(а), отменено:\n\n"
        f"🎭 <b>{h(show.title)}</b>\n"
        f"📅 {h(format_local(show.show_date))}\n"
        f"📍 {h(show.location)}, {h(show.city)}\n\n"
        "Приносим извинения! Следи за новыми анонсами 🎭"
    )
    sent = failed = offset = 0
    while True:
        async with AsyncSessionLocal() as session:
            telegram_ids = list((await session.scalars(
                select(User.telegram_id)
                .join(Registration, Registration.user_id == User.id)
                .where(Registration.show_id == show_id, Registration.is_cancelled == False)
                .order_by(User.id)
                .offset(offset).limit(100)
            )).all())
        if not telegram_ids:
            break
        for start in range(0, len(telegram_ids), 5):
            results = await asyncio.gather(*(
                send_with_retry(public_bot.send_message, telegram_id, personal_text)
                for telegram_id in telegram_ids[start:start + 5]
            ), return_exceptions=True)
            sent += sum(not isinstance(result, Exception) for result in results)
            failed += sum(isinstance(result, Exception) for result in results)
        offset += len(telegram_ids)
        if len(telegram_ids) < 100:
            break
    return web.json_response({"id": show_id, "sent": sent, "failed": failed})


async def miniapp_show_analytics(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    registration_source = func.coalesce(Registration.source, "direct")
    manual_source = func.coalesce(ManualAttendee.source, "manual")
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        reg_summary = (await session.execute(select(
            func.coalesce(func.sum(case((Registration.is_cancelled == False, 1 + Registration.guests), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == True, 1), else_=0)), 0),
            func.coalesce(func.sum(case((
                (Registration.is_cancelled == False) & (Registration.confirmed == True),
                1 + Registration.guests,
            ), else_=0)), 0),
            func.coalesce(func.sum(case((Registration.is_cancelled == False, Registration.checked_in_count), else_=0)), 0),
        ).where(Registration.show_id == show_id))).one()
        manual_summary = (await session.execute(select(
            func.count(ManualAttendee.id),
            func.coalesce(func.sum(ManualAttendee.checked_in_count), 0),
        ).where(ManualAttendee.show_id == show_id))).one()
        feedback_summary = (await session.execute(select(
            func.count(ShowFeedback.id), func.coalesce(func.avg(ShowFeedback.rating), 0),
        ).where(ShowFeedback.show_id == show_id))).one()
        rating_rows = (await session.execute(
            select(ShowFeedback.rating, func.count(ShowFeedback.id))
            .where(ShowFeedback.show_id == show_id)
            .group_by(ShowFeedback.rating).order_by(ShowFeedback.rating.desc())
        )).all()
        reg_source_rows = (await session.execute(
            select(registration_source, func.sum(1 + Registration.guests))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
            .group_by(registration_source)
        )).all()
        manual_source_rows = (await session.execute(
            select(manual_source, func.count(ManualAttendee.id))
            .where(ManualAttendee.show_id == show_id)
            .group_by(manual_source)
        )).all()
        comments = (await session.execute(
            select(ShowFeedback, User)
            .join(User, User.id == ShowFeedback.user_id)
            .where(ShowFeedback.show_id == show_id, ShowFeedback.comment.isnot(None), ShowFeedback.comment != "")
            .order_by(ShowFeedback.created_at.desc()).limit(100)
        )).all()

    sources: dict[str, int] = {}
    for source, count in [*reg_source_rows, *manual_source_rows]:
        key = str(source)
        sources[key] = sources.get(key, 0) + int(count or 0)
    registered = int(reg_summary[0]) + int(manual_summary[0])
    arrived = (
        int(show.checkin_counter or 0) if show.checkin_mode == "counter"
        else int(reg_summary[3]) + int(manual_summary[1])
    )
    return web.json_response({
        "registered": registered,
        "capacity": show.max_seats,
        "cancelledRegistrations": int(reg_summary[1]),
        "confirmed": int(reg_summary[2]),
        "arrived": arrived,
        "checkinEnabled": show.checkin_enabled,
        "feedbackEnabled": show.feedback_enabled,
        "feedbackCount": int(feedback_summary[0]),
        "averageRating": round(float(feedback_summary[1]), 1),
        "ratingDistribution": {str(rating): int(count) for rating, count in rating_rows},
        "sources": [
            {"source": source, "count": count}
            for source, count in sorted(sources.items(), key=lambda item: (-item[1], item[0]))
        ],
        "comments": [{
            "id": feedback.id,
            "rating": feedback.rating,
            "comment": feedback.comment,
            "username": user.username,
            "name": " ".join(part for part in (user.first_name, user.last_name) if part) or feedback.user_id,
            "createdAt": feedback.created_at.isoformat(),
        } for feedback, user in comments],
        "commentsLimit": 100,
    })


def _csv_value(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


async def miniapp_export_show_csv(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow([
        "Имя", "Telegram", "Доп. гости", "Статус записи", "Подтверждение",
        "Пришло фактически", "Источник", "Оценка", "Отзыв",
    ])
    source_labels = {
        "direct": "Прямая ссылка", "instagram": "Instagram", "channel": "Telegram-канал",
        "team": "Команда", "manual": "Добавлен вручную", "social": "Другие соцсети",
    }
    row_count = 0
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        registration_rows = await session.stream(
            select(Registration, User, ShowFeedback)
            .join(User, User.id == Registration.user_id)
            .outerjoin(ShowFeedback, (ShowFeedback.show_id == show_id) & (ShowFeedback.user_id == User.id))
            .where(Registration.show_id == show_id)
            .order_by(Registration.id).limit(10_000)
        )
        async for registration, user, feedback in registration_rows:
            writer.writerow([
                _csv_value(registration.attendee_name),
                _csv_value(f"@{user.username}" if user.username else user.telegram_id),
                registration.guests or 0,
                "Отменена" if registration.is_cancelled else "Активна",
                "Да" if registration.confirmed is True else "Нет" if registration.confirmed is False else "Не отвечал(а)",
                registration.checked_in_count or 0,
                _csv_value(source_labels.get(registration.source or "direct", registration.source or "Прямая ссылка")),
                feedback.rating if feedback else "",
                _csv_value(feedback.comment if feedback else ""),
            ])
            row_count += 1
        if row_count < 10_000:
            manual_rows = await session.stream(
                select(ManualAttendee).where(ManualAttendee.show_id == show_id)
                .order_by(ManualAttendee.id).limit(10_000 - row_count)
            )
            async for attendee in manual_rows.scalars():
                writer.writerow([
                    _csv_value(attendee.name), _csv_value(attendee.contact), 0, "Добавлен вручную",
                    "Не требуется", attendee.checked_in_count or 0,
                    _csv_value(source_labels.get(attendee.source or "manual", attendee.source or "Добавлен вручную")),
                    "", "",
                ])
    data = ("\ufeff" + output.getvalue()).encode("utf-8")
    return web.Response(
        body=data, content_type="text/csv", charset="utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="show-{show_id}-attendees.csv"',
            "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        },
    )


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
        if len(content) > 8 * 1024 * 1024:
            raise web.HTTPRequestEntityTooLarge(max_size=8 * 1024 * 1024, actual_size=len(content))
    if not content:
        raise web.HTTPBadRequest(text=json.dumps({"error": "empty_poster"}), content_type="application/json")
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format not in {"JPEG", "PNG", "WEBP"} or image.width * image.height > 40_000_000:
                raise ValueError
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        logger.warning("Poster upload rejected: invalid image content_type=%s size=%s", content_type or "missing", len(content))
        raise web.HTTPBadRequest(
            text=json.dumps({"error": "invalid_poster"}), content_type="application/json",
        )
    bot = request.app[ADMIN_BOT_KEY]
    message = await bot.send_photo(
        creator_telegram_id,
        BufferedInputFile(bytes(content), filename=part.filename or "poster.jpg"),
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


def _require_admin(request: web.Request) -> None:
    if not request["miniapp_is_admin"]:
        raise web.HTTPForbidden(
            text=json.dumps({"error": "admin_access_required"}),
            content_type="application/json",
        )


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
        "posterText", "maxSeats", "registrarUsername", "checkinEnabled", "feedbackEnabled",
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


async def miniapp_create_show(request: web.Request) -> web.Response:
    fields = _show_fields(await _json_body(request), require_all=True)
    async with AsyncSessionLocal() as session:
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


async def miniapp_send_show_preview(request: web.Request) -> web.Response:
    fields = _show_fields(await _json_body(request), require_all=True)
    preview = SimpleNamespace(
        title=fields["title"], team_name=fields["team_name"],
        show_date=fields["show_date"], location=fields["location"],
        location_url=fields.get("location_url"), city=fields["city"],
        max_seats=fields["max_seats"], poster_text=fields.get("poster_text"),
        registrar_username=fields.get("registrar_username"), registrar=None,
    )
    from scheduler.jobs import build_announcement_text
    text = "🧪 <b>Предпросмотр — сообщение не опубликовано</b>\n\n" + build_announcement_text(
        preview, seats_left=int(fields["max_seats"]),
    )
    bot = request.app[ADMIN_BOT_KEY]
    await send_with_retry(
        bot.send_message, request["miniapp_telegram_id"], text,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    return web.json_response({"sent": True})


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
        if "registrar_username" in fields:
            username = fields["registrar_username"]
            registrar = await crud.get_user_by_username(session, str(username)) if username else None
            fields["registrar_id"] = registrar.id if registrar else None
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


async def miniapp_show_tasks(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        registrations = await crud.get_registered_users_for_show(session, show_id)
        pending_manual = await crud.get_pending_manual_attendees_for_reminder(session, show_id, limit=100)
        announced = await crud.has_any_announcement_been_sent(session, show_id)
        tasks = []
        if not announced: tasks.append({"key": "announcement", "label": "Опубликовать анонс", "count": 1})
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


async def miniapp_registration_chat(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if any(key not in {"target", "nameMode"} for key in data):
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    target_raw = _required_text(data, "target", 128)
    name_mode = data.get("nameMode", "short")
    if name_mode not in {"short", "full"}:
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
        await crud.update_show(session, show_id, registration_chat_id=chat.id, registration_chat_title=display_name, registration_chat_name_mode=name_mode)
    return web.json_response({"id": chat.id, "title": display_name, "nameMode": name_mode})


async def miniapp_clear_registration_chat(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        await crud.update_show(session, show_id, registration_chat_id=None, registration_chat_title=None)
    return web.json_response({"id": show_id})


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
        await _manageable_api_show(session, request, show_id)
        if not await crud.delete_show(session, show_id):
            raise web.HTTPConflict(text=json.dumps({"error": "delete_rejected"}), content_type="application/json")
    await _record_audit(request, "show.deleted", "show", show_id)
    return web.json_response({"id": show_id})


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


async def miniapp_attendees(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        offset = max(0, int(request.query.get("offset", "0")))
    except ValueError:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_offset"}), content_type="application/json")
    limit = 100
    search = request.query.get("search", "").strip()[:100]
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        registrations_query = (
            select(Registration)
            .join(User, User.id == Registration.user_id)
            .options(selectinload(Registration.user))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
            .order_by(Registration.registered_at, Registration.id)
            .offset(offset).limit(limit + 1)
        )
        manual_query = (
            select(ManualAttendee)
            .where(ManualAttendee.show_id == show_id)
            .order_by(ManualAttendee.added_at, ManualAttendee.id)
            .offset(offset).limit(limit + 1)
        )
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
        occupied = await crud.count_active_registrations(session, show_id)
        arrived = int(await session.scalar(
            select(func.coalesce(func.sum(Registration.checked_in_count), 0))
            .where(Registration.show_id == show_id, Registration.is_cancelled == False)
        ) or 0) + int(await session.scalar(
            select(func.coalesce(func.sum(ManualAttendee.checked_in_count), 0))
            .where(ManualAttendee.show_id == show_id)
        ) or 0)
        has_more = len(registrations) > limit or len(manual) > limit
        return web.json_response({
            "occupied": occupied, "maxSeats": show.max_seats, "arrived": arrived,
            "hasMore": has_more, "nextOffset": offset + limit,
            "registrations": [{
                "id": item.id, "name": item.attendee_name, "guests": item.guests or 0,
                "username": item.user.username, "confirmed": item.confirmed,
                "checkedInCount": item.checked_in_count or 0, "source": item.source,
            } for item in registrations[:limit]],
            "manual": [{
                "id": item.id, "name": item.name, "contact": item.contact,
                "checkedInCount": item.checked_in_count or 0, "source": item.source,
            } for item in manual[:limit]],
        })


async def miniapp_add_manual_attendees(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    data = await _json_body(request)
    if set(data) != {"rows"} or not isinstance(data["rows"], list) or not 1 <= len(data["rows"]) <= 50:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    names: list[str] = []
    contacts: list[str | None] = []
    for row in data["rows"]:
        if not isinstance(row, dict) or any(key not in {"name", "contact"} for key in row):
            raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
        names.append(_required_text(row, "name", 100))
        contacts.append(_optional_text(row, "contact", 512))
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        added = await crud.add_manual_attendees(
            session, show_id, names, source="manual", contacts=contacts,
        )
        if added != len(names):
            raise web.HTTPConflict(
                text=json.dumps({"error": "capacity_exceeded"}), content_type="application/json",
            )
        return web.json_response({"added": added}, status=201)


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
            if isinstance(guests, bool) or not isinstance(guests, int) or not 0 <= guests <= 50:
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
        return web.json_response({"id": registration_id})


async def miniapp_update_manual_attendee(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        attendee_id = int(request.match_info["attendee_id"])
    except ValueError:
        raise web.HTTPNotFound()
    data = await _json_body(request)
    if set(data) != {"checkedInCount"}:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_payload"}), content_type="application/json")
    count = data["checkedInCount"]
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1:
        raise web.HTTPBadRequest(text=json.dumps({"error": "invalid_field", "field": "checkedInCount"}), content_type="application/json")
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        updated = await crud.set_manual_checkin_count(session, show_id, attendee_id, count)
        if updated is None:
            raise web.HTTPNotFound()
        return web.json_response({"id": updated.id})


async def miniapp_delete_manual_attendee(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    try:
        attendee_id = int(request.match_info["attendee_id"])
    except ValueError:
        raise web.HTTPNotFound()
    async with AsyncSessionLocal() as session:
        await _manageable_api_show(session, request, show_id)
        attendee = await session.scalar(select(ManualAttendee).where(
            ManualAttendee.id == attendee_id, ManualAttendee.show_id == show_id,
        ))
        if attendee is None:
            raise web.HTTPNotFound()
        await crud.delete_manual_attendee(session, attendee_id)
        return web.json_response({"id": attendee_id})


async def miniapp_index(request: web.Request) -> web.FileResponse:
    index = MINIAPP_DIST / "index.html"
    if not index.is_file():
        raise web.HTTPServiceUnavailable(text="Mini App frontend is not built")
    return web.FileResponse(index)


def register_miniapp_routes(app: web.Application) -> None:
    app.middlewares.append(miniapp_security_headers_middleware)
    app.middlewares.append(miniapp_request_logging_middleware)
    app.middlewares.append(miniapp_auth_middleware)
    app.router.add_get("/api/miniapp/me", miniapp_me)
    app.router.add_get("/api/miniapp/shows", miniapp_shows)
    app.router.add_post("/api/miniapp/shows", miniapp_create_show)
    app.router.add_post("/api/miniapp/shows/preview", miniapp_send_show_preview)
    app.router.add_get("/api/miniapp/shows/{show_id}", miniapp_show_detail)
    app.router.add_patch("/api/miniapp/shows/{show_id}", miniapp_update_show)
    app.router.add_delete("/api/miniapp/shows/{show_id}", miniapp_delete_show)
    app.router.add_post("/api/miniapp/shows/{show_id}/restore", miniapp_restore_show)
    app.router.add_get("/api/miniapp/options", miniapp_options)
    app.router.add_get("/api/miniapp/access/users", miniapp_access_users)
    app.router.add_get("/api/miniapp/audit-log", miniapp_audit_log)
    app.router.add_post("/api/miniapp/access/invites", miniapp_create_access_invite)
    app.router.add_patch("/api/miniapp/access/users/{user_id}", miniapp_update_access_user)
    app.router.add_post("/api/miniapp/teams", miniapp_create_team)
    app.router.add_patch("/api/miniapp/teams/{team_id}", miniapp_update_team)
    app.router.add_delete("/api/miniapp/teams/{team_id}", miniapp_delete_team)
    app.router.add_post("/api/miniapp/venues", miniapp_create_venue)
    app.router.add_patch("/api/miniapp/venues/{venue_id}", miniapp_update_venue)
    app.router.add_delete("/api/miniapp/venues/{venue_id}", miniapp_delete_venue)
    app.router.add_post("/api/miniapp/ad-channels", miniapp_create_ad_channel)
    app.router.add_patch("/api/miniapp/ad-channels/{channel_id}/toggle", miniapp_toggle_ad_channel)
    app.router.add_delete("/api/miniapp/ad-channels/{channel_id}", miniapp_delete_ad_channel)
    app.router.add_get("/api/miniapp/shows/{show_id}/attendees", miniapp_attendees)
    app.router.add_get("/api/miniapp/shows/{show_id}/tasks", miniapp_show_tasks)
    app.router.add_post("/api/miniapp/shows/{show_id}/remind", miniapp_remind_viewers)
    app.router.add_put("/api/miniapp/shows/{show_id}/registration-chat", miniapp_registration_chat)
    app.router.add_delete("/api/miniapp/shows/{show_id}/registration-chat", miniapp_clear_registration_chat)
    app.router.add_post("/api/miniapp/registration-chat/verify", miniapp_verify_registration_chat)
    app.router.add_post("/api/miniapp/shows/{show_id}/manual-notifications/confirm", miniapp_confirm_manual_notifications)
    app.router.add_post("/api/miniapp/shows/{show_id}/attendees/manual", miniapp_add_manual_attendees)
    app.router.add_patch("/api/miniapp/shows/{show_id}/registrations/{registration_id}", miniapp_update_registration)
    app.router.add_delete("/api/miniapp/shows/{show_id}/registrations/{registration_id}", miniapp_cancel_registration)
    app.router.add_patch("/api/miniapp/shows/{show_id}/manual-attendees/{attendee_id}", miniapp_update_manual_attendee)
    app.router.add_delete("/api/miniapp/shows/{show_id}/manual-attendees/{attendee_id}", miniapp_delete_manual_attendee)
    app.router.add_get("/api/miniapp/shows/{show_id}/announcement-preview", miniapp_announcement_preview)
    app.router.add_get("/api/miniapp/shows/{show_id}/promotion", miniapp_promotion)
    app.router.add_post("/api/miniapp/shows/{show_id}/publish", miniapp_publish)
    app.router.add_post("/api/miniapp/shows/{show_id}/clone", miniapp_clone_show)
    app.router.add_post("/api/miniapp/shows/{show_id}/cancel", miniapp_cancel_show)
    app.router.add_get("/api/miniapp/shows/{show_id}/qr", miniapp_show_qr)
    app.router.add_get("/api/miniapp/shows/{show_id}/analytics", miniapp_show_analytics)
    app.router.add_get("/api/miniapp/shows/{show_id}/export.csv", miniapp_export_show_csv)
    app.router.add_post("/api/miniapp/shows/{show_id}/poster", miniapp_upload_poster)
    app.router.add_get("/api/miniapp/shows/{show_id}/poster", miniapp_poster)
    app.router.add_get("/app", miniapp_index)
    if MINIAPP_DIST.is_dir():
        app.router.add_static("/app/assets", MINIAPP_DIST / "assets", show_index=False)
