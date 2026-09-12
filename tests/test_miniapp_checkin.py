from tests.miniapp_support import *
import miniapp_checkin as checkin
from db.models import ShowCheckinStaff
from checkin_service import arrival_stats, notify_arrivals


@pytest.mark.asyncio
async def test_door_staff_counts_search_permissions_and_reports(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(checkin, "AsyncSessionLocal", sessions)
        async with sessions() as session:
            owner, staff, viewer = User(telegram_id=701, role=UserRole.organizer), User(telegram_id=702), User(telegram_id=703)
            session.add_all([owner, staff, viewer]); await session.flush()
            show = Show(title="Вход", team_name="Команда", show_date=utc_now() + timedelta(hours=1), location="Театр", city="Лимасол",
                        creator_id=owner.id, checkin_enabled=True, checkin_mode="counter", checkin_report_every=3, registration_chat_id=-100)
            session.add(show); await session.flush()
            session.add(ShowCheckinStaff(show_id=show.id, user_id=staff.id, expires_at=utc_now() + timedelta(hours=12)))
            reg = Registration(show_id=show.id, user_id=viewer.id, attendee_name="Анна", guests=2)
            manual = ManualAttendee(show_id=show.id, name="Борис", guests=1)
            session.add_all([reg, manual]); await session.commit()
            show_id, staff_id, owner_id, reg_id, manual_id = show.id, staff.id, owner.id, reg.id, manual.id
        invite_request = _Request(show_id=show_id, user_id=owner_id)
        invite_response = json.loads((await checkin.miniapp_checkin_invite(invite_request)).text)
        token = invite_response["url"].split("door_", 1)[1]
        async with sessions() as session:
            assert await crud.consume_checkin_invite(session, token, staff_id) == show_id
            assert await crud.consume_checkin_invite(session, token, staff_id) is None
        request = _Request(show_id=show_id, user_id=staff_id, body={"delta": 2, "expected": 0})
        bot = AsyncMock(); request.app = {checkin.ADMIN_BOT_KEY: bot}
        first = json.loads((await checkin.miniapp_checkin_update(request)).text)
        assert first == {"arrived": 2, "booked": 5, "remaining": 3, "percent": 40.0}
        bot.send_message.assert_not_awaited()
        with pytest.raises(web.HTTPConflict):
            await checkin.miniapp_checkin_update(request)
        request._body = {"delta": 1, "expected": 2}
        await checkin.miniapp_checkin_update(request)
        assert "60.0%" in bot.send_message.await_args.args[1]
        assert "ждут начала" in bot.send_message.await_args.args[1]
        async with sessions() as session:
            show = await session.get(Show, show_id)
            await notify_arrivals(bot, session, show, await arrival_stats(session, show))
        assert bot.send_message.await_count == 1
        request._body = {"mode": "named", "reportEvery": 5}
        with pytest.raises(web.HTTPNotFound):
            await checkin.miniapp_checkin_config(request)
        owner_request = _Request(show_id=show_id, user_id=owner_id, body=request._body)
        with pytest.raises(web.HTTPConflict):
            await checkin.miniapp_checkin_config(owner_request)
        async with sessions() as session:
            await crud.update_show(session, show_id, checkin_counter=0, checkin_mode="named")
        request.query = {"search": "Анна"}
        result = json.loads((await checkin.miniapp_checkin(request)).text)
        assert [(entry["name"], entry["booked"]) for entry in result["items"]] == [("Анна", 3)]
        request._body = {"kind": "registration", "id": reg_id, "count": 3, "arrived": 0}
        await checkin.miniapp_checkin_update(request)
        request._body = {"kind": "manual", "id": manual_id, "count": 2, "arrived": 0}
        assert json.loads((await checkin.miniapp_checkin_update(request)).text)["percent"] == 100
        request._body = {"kind": "manual", "id": manual_id, "count": 3, "arrived": 2}
        with pytest.raises(web.HTTPBadRequest):
            await checkin.miniapp_checkin_update(request)
        stranger = _Request(show_id=show_id, user_id=viewer.id)
        with pytest.raises(web.HTTPNotFound):
            await checkin.miniapp_checkin(stranger)
        async with sessions() as session:
            access = await session.get(ShowCheckinStaff, (show_id, staff_id)); access.expires_at = utc_now() - timedelta(seconds=1)
            await session.commit()
        with pytest.raises(web.HTTPNotFound):
            await checkin.miniapp_checkin(request)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_staff_miniapp_auth_restricts_admin_endpoints(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(miniapp_api, "AsyncSessionLocal", sessions)
        monkeypatch.setattr(miniapp_api.settings, "ADMIN_BOT_TOKEN", BOT_TOKEN)
        monkeypatch.setattr(miniapp_api.time, "time", lambda: NOW)
        async with sessions() as session:
            user = User(telegram_id=42); session.add(user); await session.flush()
            show = Show(title="Шоу", team_name="Команда", show_date=utc_now(), location="Театр", city="Лимасол", creator_id=user.id)
            session.add(show); await session.flush()
            session.add(ShowCheckinStaff(show_id=show.id, user_id=user.id, expires_at=utc_now() + timedelta(hours=1)))
            await session.commit()
        request = _Request(show_id=show.id, user_id=user.id)
        request.headers = {"Authorization": f"tma {_signed_init_data()}"}
        request.path = "/api/miniapp/me"
        response = await miniapp_api.miniapp_auth_middleware(request, miniapp_api.miniapp_me)
        assert json.loads(response.text)["role"] == "checkin"
        request.path = "/api/miniapp/options"
        with pytest.raises(web.HTTPForbidden):
            await miniapp_api.miniapp_auth_middleware(request, AsyncMock())
        monkeypatch.setattr(miniapp_api.time, "time", lambda: NOW + 3600)
        request.path = f"/api/miniapp/shows/{show.id}/checkin"
        handler = AsyncMock(return_value=web.json_response({"ok": True}))
        assert (await miniapp_api.miniapp_auth_middleware(request, handler)).status == 200
    finally:
        await engine.dispose()
