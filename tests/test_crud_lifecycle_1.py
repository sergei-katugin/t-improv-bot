from tests.crud_lifecycle_support import *


@pytest.mark.asyncio
async def test_invite_is_single_use_and_grants_role():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, _ = await _fixture(session)
            invite = await crud.create_invite_token(session, UserRole.organizer)

            stored = await session.get(InviteToken, invite.id)
            assert stored.token == hashlib.sha256(invite.token.encode()).hexdigest()
            assert stored.token != invite.token

            assert await crud.consume_invite_token(session, invite.token, viewer.id) is not None
            assert await crud.consume_invite_token(session, invite.token, viewer.id) is None
            await session.refresh(viewer)
            assert viewer.role == UserRole.organizer
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_registration_releases_capacity():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=2)
            assert await crud.count_active_registrations(session, show.id) == 3

            await crud.cancel_registration(session, show.id, viewer.id)

            assert await crud.count_active_registrations(session, show.id) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registration_respects_guest_limit_and_auto_close():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            show.max_seats = 20
            show.max_guests = 1
            await session.commit()

            assert await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=2) is None
            show.registration_closes_at = utc_now() - timedelta(minutes=1)
            await session.commit()
            assert await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=1) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_waitlist_promotes_first_viewer_when_a_place_is_released():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            _, viewer, show = await _fixture(session)
            waiting = User(telegram_id=1003, first_name="Waiting")
            session.add(waiting)
            await session.commit()
            await crud.register_user_safe(session, show.id, viewer.id, "Viewer", guests=2)
            entry, position = await crud.join_waitlist(session, show.id, waiting.id, "Waiting")
            assert entry is not None and position == 1

            await crud.cancel_registration(session, show.id, viewer.id)
            promoted = await crud.promote_waitlist(session, show.id)

            assert promoted is not None
            registration, user = promoted
            assert user.id == waiting.id
            assert registration.attendee_name == "Waiting"
            assert await crud.promote_waitlist(session, show.id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_user_data_erasure_deletes_viewer_and_anonymizes_required_creator():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            creator, viewer, show = await _fixture(session)
            await crud.register_user_safe(session, show.id, viewer.id, "Private Name", guests=0)

            await crud.delete_or_anonymize_user_data(session, viewer)
            assert await session.get(User, viewer.id) is None

            creator_id = creator.id
            await crud.delete_or_anonymize_user_data(session, creator)
            anonymous = await session.get(User, creator_id)
            assert anonymous is not None
            assert anonymous.telegram_id == -creator_id
            assert anonymous.first_name is None
            assert anonymous.username is None
    finally:
        await engine.dispose()
