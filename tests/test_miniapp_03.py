from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_attention_center_reports_actionable_upcoming_shows(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=990, role=UserRole.organizer)
            session.add(owner); await session.flush()
            show = Show(title="Needs work", team_name="Team", show_date=utc_now() + timedelta(days=2), location="Venue", city="City", max_seats=20, creator_id=owner.id)
            session.add(show); await session.commit(); owner_id = owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        statements = []
        event.listen(
            engine.sync_engine, "before_cursor_execute",
            lambda *_args: statements.append(_args[2]),
        )
        payload = json.loads((await miniapp_api.miniapp_attention(_Request(show_id=0, user_id=owner_id))).text)
        assert {item["kind"] for item in payload["items"]} == {"announcement", "chat", "edit"}
        assert len(statements) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_access_role_update_protects_self_and_admin_but_revokes_organizer(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=1000, username="admin", role=UserRole.admin)
            organizer = User(telegram_id=1001, username="organizer", role=UserRole.organizer)
            session.add_all([admin, organizer])
            await session.commit()
            admin_id, organizer_id = admin.id, organizer.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        self_request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"role": "user"})
        self_request.match_info = {"user_id": str(admin_id)}
        with pytest.raises(web.HTTPConflict):
            await miniapp_api.miniapp_update_access_user(self_request)

        revoke_request = _Request(show_id=0, user_id=admin_id, is_admin=True, body={"role": "user"})
        revoke_request.match_info = {"user_id": str(organizer_id)}
        response = await miniapp_api.miniapp_update_access_user(revoke_request)
        assert response.status == 200
        async with sessions() as session:
            organizer = await session.get(User, organizer_id)
            assert organizer is not None and organizer.role == UserRole.user
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_access_invite_is_organizer_only_and_expires(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=0, user_id=1, is_admin=True, body={"role": "organizer"})
        response = await miniapp_api.miniapp_create_access_invite(request)
        payload = json.loads(response.text)
        assert response.status == 201
        assert payload["role"] == "organizer"
        assert payload["expiresAt"] is not None
        assert "?start=inv_" in payload["url"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_audit_log_records_actor_and_is_admin_only(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            admin = User(telegram_id=1100, username="audit_admin", role=UserRole.admin)
            session.add(admin)
            await session.commit()
            admin_id = admin.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=42, user_id=admin_id, is_admin=True)
        await miniapp_api._record_audit(
            request, "show.cancelled", "show", 42, {"safe": True},
        )
        response = await miniapp_api.miniapp_audit_log(request)
        payload = json.loads(response.text)
        assert payload["items"][0]["action"] == "show.cancelled"
        assert payload["items"][0]["actor"]["username"] == "audit_admin"
        assert payload["items"][0]["details"] == {"safe": True}
        async with sessions() as session:
            assert await session.scalar(miniapp_api.select(AuditLog)) is not None

        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_audit_log(
                _Request(show_id=42, user_id=admin_id, is_admin=False),
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_list_filters_by_team_year_and_paginates(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1200, role=UserRole.organizer)
            session.add(owner); await session.flush()
            first_show = Show(title="First", team_name="Alpha", show_date=utc_now() + timedelta(days=10), location="V", city="C", max_seats=10, creator_id=owner.id)
            session.add_all([
                first_show,
                Show(title="Second", team_name="Alpha", show_date=utc_now() + timedelta(days=9), location="V", city="C", max_seats=10, creator_id=owner.id),
                Show(title="Other", team_name="Beta", show_date=utc_now() + timedelta(days=8), location="V", city="C", max_seats=10, creator_id=owner.id),
            ])
            await session.flush()
            session.add(AnnouncementLog(show_id=first_show.id, announcement_type="manual"))
            await session.commit(); owner_id = owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(miniapp_api, "MAX_SHOWS_PER_PAGE", 1)
        request = _Request(show_id=0, user_id=owner_id)
        request.query = {"status": "upcoming", "team": "Alpha", "year": str((utc_now() + timedelta(days=10)).year), "offset": "0"}
        first = json.loads((await miniapp_api.miniapp_shows(request)).text)
        assert [item["teamName"] for item in first["items"]] == ["Alpha"]
        assert first["items"][0]["hasPublished"] is True
        assert first["hasMore"] is True and first["nextOffset"] == 1
        assert first["nextCursor"]
        request.query.pop("offset")
        request.query["cursor"] = first["nextCursor"]
        second = json.loads((await miniapp_api.miniapp_shows(request)).text)
        assert len(second["items"]) == 1 and second["hasMore"] is False
        assert second["items"][0]["hasPublished"] is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attendee_search_matches_name_username_and_manual_contact(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1300, role=UserRole.organizer)
            viewer = User(telegram_id=1301, username="find_me")
            session.add_all([owner, viewer]); await session.flush()
            show = Show(title="Search", team_name="Team", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=20, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=viewer.id, attendee_name="Telegram Viewer"),
                ManualAttendee(show_id=show.id, name="Manual Viewer", contact="@manual_find"),
            ])
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id); request.query = {"search": "find_me"}
        by_username = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert [item["username"] for item in by_username["registrations"]] == ["find_me"]
        request.query = {"search": "manual_find"}
        by_contact = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert [item["name"] for item in by_contact["manual"]] == ["Manual Viewer"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attendee_cursor_pages_each_source_without_reloading_waitlist(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1310, role=UserRole.organizer)
            viewers = [User(telegram_id=1400 + index) for index in range(51)]
            session.add_all([owner, *viewers]); await session.flush()
            show = Show(title="Paged", team_name="Team", show_date=utc_now() + timedelta(days=1), location="V", city="C", max_seats=200, creator_id=owner.id)
            session.add(show); await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=user.id, attendee_name=f"Viewer {index}")
                for index, user in enumerate(viewers)
            ] + [
                ManualAttendee(show_id=show.id, name=f"Manual {index}") for index in range(51)
            ])
            await session.commit(); show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(show_id=show_id, user_id=owner_id); request.query = {}
        first = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert len(first["registrations"]) == len(first["manual"]) == 50
        assert first["hasMore"] is True and first["nextCursor"]
        request.query = {"cursor": first["nextCursor"]}
        second = json.loads((await miniapp_api.miniapp_attendees(request)).text)
        assert len(second["registrations"]) == len(second["manual"]) == 1
        assert second["hasMore"] is False and second["waitlist"] == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dictionary_delete_enforces_owner_and_admin_roles(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=1400, role=UserRole.organizer)
            other = User(telegram_id=1401, role=UserRole.organizer)
            session.add_all([owner, other]); await session.flush()
            team = await miniapp_api.crud.create_team(session, "Owned", None, owner.id)
            team_id, owner_id, other_id = team.id, owner.id, other.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        denied = _Request(show_id=0, user_id=other_id); denied.match_info = {"team_id": str(team_id)}
        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_delete_team(denied)
        allowed = _Request(show_id=0, user_id=owner_id); allowed.match_info = {"team_id": str(team_id)}
        assert (await miniapp_api.miniapp_delete_team(allowed)).status == 200

        venue_request = _Request(show_id=0, user_id=owner_id, body={"name": "V", "city": "C", "defaultSeats": 10})
        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_create_venue(venue_request)
    finally:
        await engine.dispose()
