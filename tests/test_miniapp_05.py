from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_poster_upload_rejects_invalid_content_type_before_telegram(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2200, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Poster", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add(show); await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        part = SimpleNamespace(name="poster", headers={"Content-Type": "text/html"})
        request = _Request(show_id=show_id, user_id=owner_id)
        request.multipart = AsyncMock(return_value=SimpleNamespace(next=AsyncMock(return_value=part)))
        with pytest.raises(web.HTTPBadRequest) as error:
            await miniapp_api.miniapp_upload_poster(request)
        assert json.loads(error.value.text) == {"error": "unsupported_poster_type"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_can_manage_venues_and_ad_channels(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=2300, role=UserRole.admin)
            session.add(admin); await session.commit(); admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"name": "Venue", "city": "City", "mapsUrl": "https://maps.example/v", "defaultSeats": 25})
        venue_id = json.loads((await miniapp_api.miniapp_create_venue(request)).text)["id"]
        request.match_info = {"venue_id": str(venue_id)}; request._body = {"name": "Updated", "defaultSeats": 30}
        assert (await miniapp_api.miniapp_update_venue(request)).status == 200
        async with sessions() as session:
            venue = await miniapp_api.crud.get_venue(session, venue_id)
            assert (venue.name, venue.default_seats) == ("Updated", 30)
        assert (await miniapp_api.miniapp_delete_venue(request)).status == 200

        request.match_info = {}; request._body = {"username": "@promo_channel"}
        channel_id = json.loads((await miniapp_api.miniapp_create_ad_channel(request)).text)["id"]
        request.match_info = {"channel_id": str(channel_id)}
        toggled = json.loads((await miniapp_api.miniapp_toggle_ad_channel(request)).text)
        assert toggled["isActive"] is False
        assert (await miniapp_api.miniapp_delete_ad_channel(request)).status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_mutations_validate_show_and_capacity(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=2400, role=UserRole.organizer)
            viewer = User(telegram_id=2401)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Capacity", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=2, creator_id=owner.id)
            session.add(show); await session.flush()
            registration = Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=0)
            manual = ManualAttendee(show_id=show.id, name="Manual")
            session.add_all([registration, manual]); await session.commit()
            show_id, owner_id, registration_id = show.id, owner.id, registration.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        request = _Request(show_id=show_id, user_id=owner_id, body={"guests": 1})
        request.match_info["registration_id"] = str(registration_id)
        with pytest.raises(web.HTTPConflict):
            await miniapp_api.miniapp_update_registration(request)
        request._body = {"checkedInCount": 1}
        assert (await miniapp_api.miniapp_update_registration(request)).status == 200

        request.match_info = {"show_id": str(show_id), "registration_id": str(registration_id)}
        assert (await miniapp_api.miniapp_cancel_registration(request)).status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_admin_dictionary_api_full_lifecycle(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=9001, role=UserRole.admin, first_name="Admin")
            session.add(admin)
            await session.commit()
            admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        def request(body=None, **match_info):
            value = _Request(show_id=0, user_id=admin_id, is_admin=True, body=body)
            value.match_info.update({key: str(item) for key, item in match_info.items()})
            return value

        response = await miniapp_api.miniapp_create_team(request({"name": " Новая ", "members": "@annie, @bobby"}))
        team_id = json.loads(response.text)["id"]
        assert response.status == 201
        response = await miniapp_api.miniapp_update_team(request({"name": "Обновлённая", "members": "@katie"}, team_id=team_id))
        assert response.status == 200

        response = await miniapp_api.miniapp_create_venue(request({
            "name": "Театр", "city": "Лимасол", "mapsUrl": "https://maps.example/v", "defaultSeats": 80,
        }))
        venue_id = json.loads(response.text)["id"]
        response = await miniapp_api.miniapp_update_venue(request({
            "name": "Новый театр", "city": "Пафос", "mapsUrl": "", "defaultSeats": 60,
        }, venue_id=venue_id))
        assert response.status == 200

        response = await miniapp_api.miniapp_create_ad_channel(request({"username": "@improv_news"}))
        channel_id = json.loads(response.text)["id"]
        toggled = await miniapp_api.miniapp_toggle_ad_channel(request({}, channel_id=channel_id))
        assert json.loads(toggled.text)["isActive"] is False

        options = await miniapp_api.miniapp_options(request())
        payload = json.loads(options.text)
        assert payload["teams"][0]["name"] == "Обновлённая"
        assert payload["venues"][0]["defaultSeats"] == 60
        assert payload["adChannels"][0]["username"] == "@improv_news"

        assert (await miniapp_api.miniapp_delete_ad_channel(request({}, channel_id=channel_id))).status == 200
        assert (await miniapp_api.miniapp_delete_venue(request({}, venue_id=venue_id))).status == 200
        assert (await miniapp_api.miniapp_delete_team(request({}, team_id=team_id))).status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_miniapp_me_create_update_restore_and_delete_show(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9002, role=UserRole.organizer, first_name="Owner", username="owner")
            session.add(owner)
            await session.commit()
            owner_id = owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(miniapp_api, "_record_audit", AsyncMock())
        request = _Request(show_id=0, user_id=owner_id, body=_valid_show_payload())
        request.app = {miniapp_api.PUBLIC_BOT_KEY: AsyncMock(), miniapp_api.ADMIN_BOT_KEY: AsyncMock()}

        me = json.loads((await miniapp_api.miniapp_me(request)).text)
        assert me["telegramId"] == 9002 and me["role"] == "organizer"
        assert me["isSuperAdmin"] is False
        created = await miniapp_api.miniapp_create_show(request)
        show_id = json.loads(created.text)["id"]
        assert created.status == 201

        request.match_info["show_id"] = str(show_id)
        request._body = {"title": "Изменённое шоу", "titleNewcomer": "Понятное шоу", "notify": False}
        updated = await miniapp_api.miniapp_update_show(request)
        assert json.loads(updated.text) == {"id": show_id, "notified": 0, "failed": 0}
        async with sessions() as session:
            assert (await session.get(Show, show_id)).title_newcomer == "Понятное шоу"

        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_delete_show(request)

        async with sessions() as session:
            removable = Show(title="Super delete", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=10, creator_id=owner_id)
            session.add(removable); await session.commit(); removable_id = removable.id
        super_request = _Request(show_id=removable_id, user_id=owner_id, is_admin=True, is_super_admin=True)
        assert json.loads((await miniapp_api.miniapp_delete_show(super_request)).text)["id"] == removable_id

        async with sessions() as session:
            show = await session.get(Show, show_id)
            show.is_active = False
            await session.commit()
        restored = await miniapp_api.miniapp_restore_show(request)
        assert json.loads(restored.text)["isActive"] is True

        request._body = {"confirmed": True}
        cancelled = await miniapp_api.miniapp_cancel_show(request)
        assert json.loads(cancelled.text)["sent"] == 0
        deleted = await miniapp_api.miniapp_delete_show(request)
        assert json.loads(deleted.text)["id"] == show_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dictionary_api_rejects_invalid_and_missing_resources(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=9003, role=UserRole.admin)
            session.add(admin); await session.commit(); admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"unexpected": True})
        request.match_info.update(team_id="bad", venue_id="999", channel_id="999")
        with pytest.raises(web.HTTPBadRequest):
            await miniapp_api.miniapp_create_team(request)
        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_update_team(request)
        request._body = {"name": "V", "city": "C", "mapsUrl": "bad", "defaultSeats": 10}
        with pytest.raises(web.HTTPBadRequest):
            await miniapp_api.miniapp_create_venue(request)
        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_delete_venue(request)
        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_toggle_ad_channel(request)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_and_poster_endpoints_return_real_content(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=9100, role=UserRole.organizer)
            viewer = User(telegram_id=9101, username="viewer", role=UserRole.user)
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="CSV", team_name="T", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=20, creator_id=owner.id, poster_file_id="poster-id")
            session.add(show); await session.flush()
            registration = Registration(show_id=show.id, user_id=viewer.id, attendee_name="=FORMULA", guests=1, source="instagram", confirmed=True, checked_in_count=2)
            manual = ManualAttendee(show_id=show.id, name="Manual", contact="@contact", guests=2, source="social")
            session.add_all([registration, manual]); await session.flush()
            session.add(ShowFeedback(show_id=show.id, user_id=viewer.id, rating=5, comment="Отлично"))
            await session.commit(); owner_id, show_id = owner.id, show.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id)
        bot = AsyncMock()
        request.app = {miniapp_api.ADMIN_BOT_KEY: bot}

        exported = await miniapp_api.miniapp_export_show_csv(request)
        csv_text = exported.body.decode("utf-8-sig")
        assert "'=FORMULA" in csv_text
        assert "Instagram" in csv_text and "Другие соцсети" in csv_text
        assert exported.headers["Content-Disposition"].endswith('attendees.csv"')

        bot.get_file.return_value = SimpleNamespace(file_path="photos/poster.png")
        async def download(_path, destination):
            destination.write(b"PNG-content")
        bot.download_file.side_effect = download
        poster = await miniapp_api.miniapp_poster(request)
        assert poster.body == b"PNG-content" and poster.content_type == "image/png"
    finally:
        await engine.dispose()
