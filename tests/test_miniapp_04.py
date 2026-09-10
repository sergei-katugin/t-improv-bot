from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_cancelled_show_can_be_restored_then_deleted_by_owner(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1500, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Restore", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id, is_active=False)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id)
        restored = json.loads((await miniapp_api.miniapp_restore_show(request)).text)
        assert restored["isActive"] is True
        assert (await miniapp_api.miniapp_delete_show(request)).status == 200
        async with sessions() as session:
            assert await session.get(Show, show_id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_chat_is_verified_before_it_is_saved(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1600, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Chat", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(
            get_chat=AsyncMock(return_value=SimpleNamespace(id=-100123, title="Registrations", username=None, type="channel")),
            get_me=AsyncMock(return_value=SimpleNamespace(id=999)),
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator", can_post_messages=True)),
            send_message=AsyncMock(),
        )
        request = _Request(show_id=show_id, user_id=owner_id, body={"target": "@registrations", "nameMode": "full"})
        request.app = {miniapp_api.ADMIN_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_registration_chat(request)).text)
        assert payload == {"id": -100123, "title": "Registrations", "nameMode": "full"}
        bot.send_message.assert_awaited_once()
        async with sessions() as session:
            saved = await session.get(Show, show_id)
            assert (saved.registration_chat_id, saved.registration_chat_name_mode) == (-100123, "full")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_reminders_are_sent_only_to_active_registered_users(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1700, role=UserRole.organizer)
            active = User(telegram_id=1701, username="active")
            cancelled = User(telegram_id=1702, username="cancelled")
            session.add_all([owner, active, cancelled]); await session.flush()
            show = Show(title="Reminder", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=active.id, attendee_name="Active"),
                Registration(show_id=show.id, user_id=cancelled.id, attendee_name="Cancelled", is_cancelled=True),
            ])
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(send_message=AsyncMock())
        request = _Request(show_id=show_id, user_id=owner_id); request.app = {miniapp_api.PUBLIC_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_remind_viewers(request)).text)
        assert payload == {"sent": 1, "failed": 0}
        assert bot.send_message.await_args.args[0] == 1701
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_update_notifies_viewers_only_when_requested(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1800, role=UserRole.organizer)
            viewer = User(telegram_id=1801, username="viewer")
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Before", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add(Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer"))
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        bot = SimpleNamespace(send_message=AsyncMock())
        request = _Request(show_id=show_id, user_id=owner_id, body={"title": "After <b>", "notify": True})
        request.app = {miniapp_api.PUBLIC_BOT_KEY: bot}
        payload = json.loads((await miniapp_api.miniapp_update_show(request)).text)
        assert payload == {"id": show_id, "notified": 1, "failed": 0}
        assert bot.send_message.await_args.args[0] == 1801
        assert "After &lt;b&gt;" in bot.send_message.await_args.args[1]

        bot.send_message.reset_mock()
        request._body = {"title": "Silent", "notify": False}
        payload = json.loads((await miniapp_api.miniapp_update_show(request)).text)
        assert payload["notified"] == 0
        bot.send_message.assert_not_awaited()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_tasks_and_manual_notification_confirmation(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1900, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Tasks", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add(ManualAttendee(show_id=show.id, name="Manual"))
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id)
        tasks = json.loads((await miniapp_api.miniapp_show_tasks(request)).text)["items"]
        assert {item["key"] for item in tasks} == {"announcement", "show_responsible", "auto_close", "registration_chat", "manual_notifications"}

        confirmed = json.loads((await miniapp_api.miniapp_confirm_manual_notifications(request)).text)
        assert confirmed == {"confirmed": 1}
        tasks = json.loads((await miniapp_api.miniapp_show_tasks(request)).text)["items"]
        assert "manual_notifications" not in {item["key"] for item in tasks}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_tasks_recommends_manual_repeat_for_near_underfilled_show(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1902, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Soon", team_name="T", show_date=utc_now() + timedelta(days=2), location="V", city="C", max_seats=20, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add(AnnouncementLog(show_id=show.id, announcement_type="manual"))
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        tasks = json.loads((await miniapp_api.miniapp_show_tasks(_Request(show_id=show_id, user_id=owner_id))).text)["items"]
        repeat = next(item for item in tasks if item["key"] == "repeat_announcement")
        assert repeat["label"] == "Повторить анонс"
        assert "0 из 20" in repeat["description"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_auth_middleware_rejects_invalid_signature(monkeypatch):
    class Request(dict):
        path = "/api/miniapp/me"
        headers = {"Authorization": "tma invalid"}

    def reject(*_args, **_kwargs):
        raise MiniAppAuthError("bad signature")

    monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", reject)
    handler = AsyncMock()
    with pytest.raises(web.HTTPUnauthorized) as error:
        await miniapp_api.miniapp_auth_middleware(Request(), handler)
    assert json.loads(error.value.text) == {"error": "telegram_auth_failed"}
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_auth_middleware_sets_organizer_context_and_rejects_regular_user(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            organizer = User(telegram_id=2000, role=UserRole.organizer)
            regular = User(telegram_id=2001, role=UserRole.user)
            session.add_all([organizer, regular]); await session.commit()
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        class Request(dict):
            path = "/api/miniapp/me"
            headers = {"Authorization": "tma signed"}

        handler = AsyncMock(return_value=web.json_response({"ok": True}))
        monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", lambda *_args, **_kwargs: SimpleNamespace(telegram_id=2000))
        request = Request()
        response = await miniapp_api.miniapp_auth_middleware(request, handler)
        assert response.status == 200
        assert request["miniapp_telegram_id"] == 2000
        assert request["miniapp_is_admin"] is False

        monkeypatch.setattr(miniapp_api, "validate_telegram_init_data", lambda *_args, **_kwargs: SimpleNamespace(telegram_id=2001))
        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_auth_middleware(Request(), handler)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failed_publish_releases_claim_for_retry(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2100, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(
                title="Publish failure", team_name="T", show_date=utc_now() + timedelta(days=1),
                location="V", city="C", max_seats=10, creator_id=owner.id,
                poster_text="Ready", poster_file_id=None,
            )
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr("scheduler.jobs.send_to_channel", AsyncMock(side_effect=RuntimeError("telegram unavailable")))
        request = _Request(show_id=show_id, user_id=owner_id, body={})
        request.app = {miniapp_api.PUBLIC_BOT_KEY: object(), miniapp_api.ADMIN_BOT_KEY: object()}
        with pytest.raises(RuntimeError, match="telegram unavailable"):
            await miniapp_api.miniapp_publish(request)
        async with sessions() as session:
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True
    finally:
        await engine.dispose()
