from __future__ import annotations
from miniapp_common import *
from miniapp_helpers import _audit_details, _registration_url, _require_admin




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



