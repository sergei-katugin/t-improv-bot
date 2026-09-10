from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_miniapp_request_logging_returns_traceable_internal_error():
    request = type(
        "Request", (dict,), {"path": "/api/miniapp/me", "method": "GET"},
    )()

    async def handler(_request):
        raise RuntimeError("unexpected failure")

    response = await miniapp_request_logging_middleware(request, handler)
    payload = json.loads(response.text)

    assert response.status == 500
    assert payload == {
        "error": "internal_error",
        "requestId": response.headers["X-Request-ID"],
    }


@pytest.mark.asyncio
async def test_miniapp_show_detail_hides_another_organizers_show(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=100, role=UserRole.organizer)
            other = User(telegram_id=200, role=UserRole.organizer)
            session.add_all([owner, other])
            await session.flush()
            show = Show(
                title="Private", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id, other_id = show.id, other.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        with pytest.raises(web.HTTPNotFound):
            await miniapp_api.miniapp_show_detail(
                _Request(show_id=show_id, user_id=other_id),
            )
        response = await miniapp_api.miniapp_show_detail(
            _Request(show_id=show_id, user_id=other_id, is_admin=True),
        )
        assert response.status == 200
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_announcement_claim_prevents_duplicate_publish_and_can_be_released():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=500, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Publish", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id

        async with sessions() as session:
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is False
            await miniapp_api.crud.release_announcement_claim(session, show_id, "manual")
            assert await miniapp_api.crud.claim_manual_announcement(session, show_id) is True

        async with sessions() as session:
            logs = list((await session.scalars(
                miniapp_api.select(AnnouncementLog).where(AnnouncementLog.show_id == show_id)
            )).all())
            assert [log.announcement_type for log in logs] == ["manual"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_repeat_claim_is_idempotent_per_request_key():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=600, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Repeat", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id
        async with sessions() as session:
            first_type = await miniapp_api.crud.claim_repeat_announcement(
                session, show_id, "0123456789abcdef",
            )
            assert first_type is not None
            assert await miniapp_api.crud.claim_repeat_announcement(
                session, show_id, "0123456789abcdef",
            ) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_clone_show_preserves_configuration_but_uses_new_date(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=700, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            source = Show(
                title="Clone me", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", location_url="https://maps.example/venue", city="City",
                poster_text="Poster", poster_file_id="telegram-file", max_seats=33,
                creator_id=owner.id, registrar_username="sergey", checkin_enabled=True,
                feedback_enabled=True,
            )
            session.add(source)
            await session.commit()
            show_id, owner_id = source.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        response = await miniapp_api.miniapp_clone_show(_Request(
            show_id=show_id, user_id=owner_id, body={"showDateLocal": "2099-10-10T20:30"},
        ))
        payload = json.loads(response.text)
        async with sessions() as session:
            clone = await session.get(Show, payload["id"])
            assert clone is not None
            assert (clone.title, clone.poster_file_id, clone.max_seats) == (
                "Clone me", "telegram-file", 33,
            )
            assert clone.checkin_enabled is True
            assert clone.feedback_enabled is True
            assert clone.registration_closes_at == clone.show_date - timedelta(minutes=5)
            assert clone.id != show_id
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deactivate_show_is_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=800, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Cancel", team_name="Team", show_date=utc_now() + timedelta(days=1),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            show_id = show.id
        async with sessions() as session:
            assert await miniapp_api.crud.deactivate_show(session, show_id) is True
            assert await miniapp_api.crud.deactivate_show(session, show_id) is False
            cancelled = await session.get(Show, show_id)
            assert cancelled is not None and cancelled.is_active is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_show_analytics_aggregates_people_sources_and_feedback(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=900, role=UserRole.organizer)
            viewer = User(telegram_id=901, username="viewer", first_name="Viewer")
            cancelled_viewer = User(telegram_id=902, first_name="Cancelled")
            session.add_all([owner, viewer, cancelled_viewer])
            await session.flush()
            show = Show(
                title="Analytics", team_name="Team", show_date=utc_now() - timedelta(hours=3),
                location="Venue", city="City", max_seats=20, creator_id=owner.id,
                checkin_enabled=True, feedback_enabled=True,
            )
            session.add(show)
            await session.flush()
            session.add_all([
                Registration(show_id=show.id, user_id=viewer.id, attendee_name="Viewer", guests=1, source="instagram", confirmed=True, checked_in_count=2),
                Registration(show_id=show.id, user_id=cancelled_viewer.id, attendee_name="Cancelled", is_cancelled=True),
                ManualAttendee(show_id=show.id, name="Manual", source="manual", checked_in_count=1),
                ShowFeedback(show_id=show.id, user_id=viewer.id, rating=5, comment="Great"),
            ])
            await session.commit()
            show_id, owner_id = show.id, owner.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)

        response = await miniapp_api.miniapp_show_analytics(
            _Request(show_id=show_id, user_id=owner_id),
        )
        payload = json.loads(response.text)
        assert payload["registered"] == 3
        assert payload["arrived"] == 3
        assert payload["confirmed"] == 2
        assert payload["cancelledRegistrations"] == 1
        assert payload["averageRating"] == 5.0
        assert payload["occupancyRate"] == 15
        assert payload["attendanceRate"] == 100
        assert payload["cancellationRate"] == 25
        assert payload["sources"] == [
            {"source": "instagram", "count": 2},
            {"source": "manual", "count": 1},
        ]
        assert payload["comments"][0]["comment"] == "Great"
    finally:
        await engine.dispose()
