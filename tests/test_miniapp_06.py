from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_valid_poster_upload_is_checked_sent_and_saved(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9200, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Poster", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=20, creator_id=owner.id)
            session.add(show); await session.commit(); owner_id, show_id = owner.id, show.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        optimized = b"optimized-jpeg"
        monkeypatch.setattr("miniapp_media._optimized_poster_bytes", lambda content: optimized)
        # A valid 1x1 PNG keeps the test independent of filesystem fixtures.
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")

        class Part:
            name = "poster"
            filename = "poster.png"
            headers = {"Content-Type": "image/png"}
            chunks = [png, b""]
            async def read_chunk(self, size):
                return self.chunks.pop(0)

        part = Part()
        reader = AsyncMock()
        reader.next.return_value = part
        request = _Request(show_id=show_id, user_id=owner_id)
        request.multipart = AsyncMock(return_value=reader)
        bot = AsyncMock()
        bot.send_photo.return_value = SimpleNamespace(message_id=5, photo=[SimpleNamespace(file_id="new-file")])
        request.app = {miniapp_api.ADMIN_BOT_KEY: bot}

        response = await miniapp_api.miniapp_upload_poster(request)
        assert json.loads(response.text) == {"hasPoster": True}
        uploaded = bot.send_photo.await_args.args[1]
        assert uploaded.filename == "poster.jpg" and uploaded.data == optimized
        async with sessions() as session:
            assert (await session.get(Show, show_id)).poster_file_id == "new-file"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_operational_endpoints_work_together(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9500, role=UserRole.organizer)
            viewer = User(telegram_id=9501, username="viewer", role=UserRole.user)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(
                title="Operations", team_name="Team", show_date=utc_now() + timedelta(days=2),
                location="Venue", city="City", max_seats=20, max_guests=6,
                creator_id=owner.id, poster_text="Poster text", registration_chat_id=-100,
                registration_chat_title="Working chat", checkin_enabled=True,
            )
            session.add(show); await session.flush()
            registration = Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=1)
            session.add(registration); await session.commit()
            owner_id, show_id, registration_id = owner.id, show.id, registration.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(miniapp_api, "_record_audit", AsyncMock())
        request = _Request(show_id=show_id, user_id=owner_id)
        public_bot = AsyncMock()
        admin_bot = AsyncMock()
        request.app = {miniapp_api.PUBLIC_BOT_KEY: public_bot, miniapp_api.ADMIN_BOT_KEY: admin_bot}

        detail = json.loads((await miniapp_api.miniapp_show_detail(request)).text)
        assert detail["title"] == "Operations" and detail["occupiedSeats"] == 2
        preview = json.loads((await miniapp_api.miniapp_announcement_preview(request)).text)
        assert "Свободных мест" not in preview["html"]
        assert preview["html"].startswith("🎭 <b>Команда Team представляет шоу Operations</b>")
        promotion = json.loads((await miniapp_api.miniapp_promotion(request)).text)
        assert promotion["registrationUrl"].endswith(f"show_{show_id}")

        class FakeQrImage:
            def save(self, output, format): output.write(b"\x89PNG-fake")
        class FakeQr:
            def __init__(self, **_kwargs): pass
            def add_data(self, value): self.value = value
            def make(self, **_kwargs): pass
            def make_image(self, **_kwargs): return FakeQrImage()
        monkeypatch.setitem(sys.modules, "qrcode", SimpleNamespace(QRCode=FakeQr))
        qr = await miniapp_api.miniapp_show_qr(request)
        assert qr.content_type == "image/png" and qr.body.startswith(b"\x89PNG")

        tasks = json.loads((await miniapp_api.miniapp_show_tasks(request)).text)
        assert any(item["key"] == "announcement" for item in tasks["items"])
        assert tasks["registeredUsers"] == 1
        reminder = json.loads((await miniapp_api.miniapp_remind_viewers(request)).text)
        assert reminder == {"sent": 1, "failed": 0}

        request.query = {"search": "view"}
        attendees = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert attendees["occupied"] == 2
        assert attendees["registrations"][0]["username"] == "viewer"

        request.match_info["registration_id"] = str(registration_id)
        request._body = {"guests": 2}
        assert (await miniapp_api.miniapp_update_registration(request)).status == 200
        request._body = {"checkedInCount": 2}
        assert (await miniapp_api.miniapp_update_registration(request)).status == 200

        cleared = json.loads((await miniapp_api.miniapp_clear_registration_chat(request)).text)
        assert cleared["notified"] is True
        cancelled = await miniapp_api.miniapp_cancel_registration(request)
        assert json.loads(cancelled.text)["id"] == registration_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_dashboard_publish_and_cancel_flow(monkeypatch):
    from scheduler import jobs

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=9600, username="admin", first_name="Admin", role=UserRole.admin)
            viewer = User(telegram_id=9601, username="viewer", role=UserRole.user)
            session.add_all([admin, viewer]); await session.flush()
            show = Show(
                title="Publish", team_name="Team", show_date=utc_now() + timedelta(days=2),
                location="Venue", city="City", max_seats=20, creator_id=admin.id,
                poster_text="Ready to publish", registrar_username="admin",
            )
            session.add(show); await session.flush()
            session.add(Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer"))
            session.add(AuditLog(actor_user_id=admin.id, action="show.created", entity_type="show", entity_id=show.id, details='{"ok":true}'))
            await crud.remember_registration_chat(
                session, admin.id,
                SimpleNamespace(id=-300, title="Admin chat", username=None, type=SimpleNamespace(value="supergroup")),
            )
            await session.commit(); admin_id, show_id = admin.id, show.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        audit = AsyncMock()
        monkeypatch.setattr(miniapp_api, "_record_audit", audit)
        send_channel = AsyncMock(return_value=777)
        monkeypatch.setattr(jobs, "send_to_channel", send_channel)
        request = _Request(show_id=show_id, user_id=admin_id, is_admin=True, body={})
        request.query = {}
        public_bot = AsyncMock()
        admin_bot = AsyncMock()
        request.app = {miniapp_api.PUBLIC_BOT_KEY: public_bot, miniapp_api.ADMIN_BOT_KEY: admin_bot}

        access = json.loads((await miniapp_api.miniapp_access_users(request)).text)
        assert access["items"][0]["isCurrent"] is True
        log = json.loads((await miniapp_api.miniapp_audit_log(request)).text)
        assert log["items"][0]["details"] == {"ok": True}
        attention = json.loads((await miniapp_api.miniapp_attention(request)).text)
        assert any(item["kind"] == "announcement" for item in attention["items"])
        chats = json.loads((await miniapp_api.miniapp_registration_chats(request)).text)
        assert chats["items"][0]["title"] == "Admin chat"

        admin_bot.get_chat.return_value = SimpleNamespace(id=-300, title="Admin chat", username=None, type="supergroup")
        admin_bot.get_me.return_value = SimpleNamespace(id=9600)
        admin_bot.get_chat_member.return_value = SimpleNamespace(status="administrator", can_post_messages=True)
        request._body = {"target": "-300"}
        verified = json.loads((await miniapp_api.miniapp_verify_registration_chat(request)).text)
        assert verified == {"id": -300, "title": "Admin chat"}
        request._body = {"target": "-300", "nameMode": "short"}
        connected = json.loads((await miniapp_api.miniapp_registration_chat(request)).text)
        assert connected["nameMode"] == "full"

        request._body = {}
        published = json.loads((await miniapp_api.miniapp_publish(request)).text)
        assert published == {"messageId": 777, "announcementType": "manual"}
        with pytest.raises(web.HTTPConflict) as exc_info:
            await miniapp_api.miniapp_publish(request)
        assert "already_published" in exc_info.value.text

        request._body = {"confirmed": True}
        cancelled = json.loads((await miniapp_api.miniapp_cancel_show(request)).text)
        assert cancelled == {"id": show_id, "sent": 1, "failed": 0}
        assert send_channel.await_count == 2
        public_bot.send_message.assert_awaited_once()
        assert audit.await_count == 2
    finally:
        await engine.dispose()
