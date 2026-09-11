from tests.miniapp_support import *


@pytest.mark.asyncio
async def test_miniapp_adds_manual_attendee_and_notifies_registration_chat(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=3000, role=UserRole.organizer)
            session.add(owner)
            await session.flush()
            show = Show(
                title="Премьера", team_name="Команда",
                show_date=utc_now() + timedelta(days=1), location="Театр", city="Лимасол",
                max_seats=20, max_guests=3, creator_id=owner.id,
                registration_chat_id=-100500,
            )
            session.add(show)
            await session.commit()
            owner_id, show_id = owner.id, show.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        notify = AsyncMock()
        monkeypatch.setattr(miniapp_api, "notify_manual_registration", notify)
        request = _Request(
            show_id=show_id, user_id=owner_id,
            body={"name": "Анна", "source": "telegram", "contact": "@new_viewer", "guests": 2},
        )
        request.app = {miniapp_api.ADMIN_BOT_KEY: AsyncMock()}

        response = await miniapp_api.miniapp_add_manual_attendee(request)

        assert response.status == 201
        assert json.loads(response.text) == {"kind": "manual", "occupied": 3}
        async with sessions() as session:
            attendee = (await crud.get_manual_attendees(session, show_id))[0]
            assert (attendee.name, attendee.contact, attendee.guests) == (
                "Анна", "Telegram: @new_viewer", 2,
            )
            pending = await crud.get_pending_manual_attendees_for_reminder(
                session, show_id, limit=100,
            )
            assert [item.id for item in pending] == [attendee.id]
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["automatic"] is False
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_miniapp_manual_telegram_user_gets_regular_registration(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            owner = User(telegram_id=3100, role=UserRole.organizer)
            viewer = User(telegram_id=3101, username="viewer")
            session.add_all([owner, viewer])
            await session.flush()
            show = Show(
                title="Премьера", team_name="Команда",
                show_date=utc_now() + timedelta(days=1), location="Театр", city="Лимасол",
                max_seats=20, max_guests=3, creator_id=owner.id,
            )
            session.add(show)
            await session.commit()
            owner_id, show_id = owner.id, show.id
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        request = _Request(
            show_id=show_id, user_id=owner_id,
            body={"name": "Борис", "source": "telegram", "contact": "https://t.me/Viewer", "guests": 0},
        )
        request.app = {miniapp_api.ADMIN_BOT_KEY: AsyncMock()}

        response = await miniapp_api.miniapp_add_manual_attendee(request)

        assert json.loads(response.text)["kind"] == "registration"
        async with sessions() as session:
            registrations = await crud.get_show_registrations(session, show_id)
            assert len(registrations) == 1
            assert registrations[0].attendee_name == "Борис"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("body,field", [
    ({"name": "А", "source": "other", "contact": "123", "guests": 0}, "name"),
    ({"name": "Анна", "source": "telegram", "contact": "bad", "guests": 0}, "contact"),
    ({"name": "Анна", "source": "other", "contact": "123", "guests": 7}, "guests"),
])
async def test_miniapp_manual_attendee_validates_fields(body, field):
    request = _Request(show_id=1, user_id=1, body=body)

    with pytest.raises(web.HTTPBadRequest) as error:
        await miniapp_api.miniapp_add_manual_attendee(request)

    assert json.loads(error.value.text)["field"] == field
