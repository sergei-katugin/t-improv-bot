from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _json_body, _manageable_api_show, _record_audit, _registration_url, _show_id


async def _send_test_announcement_message(bot, chat_id, show, text, keyboard) -> None:
    if show.poster_file_id and len(text) <= 1024:
        await send_with_retry(
            bot.send_photo, chat_id, show.poster_file_id,
            caption=text, reply_markup=keyboard,
        )
        return
    if show.poster_file_id:
        await send_with_retry(bot.send_photo, chat_id, show.poster_file_id)
    await send_with_retry(bot.send_message, chat_id, text, reply_markup=keyboard)


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


async def miniapp_send_test_announcement(request: web.Request) -> web.Response:
    show_id = _show_id(request)
    async with AsyncSessionLocal() as session:
        show = await _manageable_api_show(session, request, show_id)
        occupied = await crud.count_active_registrations(session, show_id)
        from scheduler.jobs import build_announcement_text
        text = (
            "🧪 <b>Тестовый анонс — виден только тебе</b>\n\n"
            + build_announcement_text(show, seats_left=max(0, show.max_seats - occupied))
        )
    registration_url = f"https://t.me/{settings.PUBLIC_BOT_USERNAME.lstrip('@')}?start=show_{show_id}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📝 Записаться на шоу", url=registration_url),
    ]])
    bot = request.app[ADMIN_BOT_KEY]
    chat_id = request["miniapp_telegram_id"]
    try:
        await asyncio.wait_for(
            _send_test_announcement_message(bot, chat_id, show, text, keyboard), timeout=15,
        )
    except asyncio.TimeoutError:
        logger.warning("Test announcement timed out show_id=%s has_poster=%s", show_id, bool(show.poster_file_id))
        raise web.HTTPGatewayTimeout(
            text=json.dumps({
                "error": "telegram_timeout",
                "message": "Telegram не ответил за 15 секунд. Попробуй отправить тест ещё раз.",
            }),
            content_type="application/json",
        )
    return web.json_response({"sent": True})


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
        missing = [name for value, name in ((show.poster_text, "posterText"),) if not value]
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
            max_guests=source.max_guests,
            registration_closes_at=show_date - timedelta(minutes=5),
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
