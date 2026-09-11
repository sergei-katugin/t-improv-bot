from __future__ import annotations
from miniapp_common import *

from miniapp_analytics import miniapp_export_show_csv
from miniapp_analytics import miniapp_show_analytics
from miniapp_attendees import miniapp_add_manual_attendee, miniapp_attendees
from miniapp_attendees import miniapp_cancel_registration
from miniapp_attendees import miniapp_update_registration
from miniapp_catalog import miniapp_create_ad_channel
from miniapp_catalog import miniapp_create_team
from miniapp_catalog import miniapp_create_venue
from miniapp_catalog import miniapp_delete_ad_channel
from miniapp_catalog import miniapp_delete_team
from miniapp_catalog import miniapp_delete_venue
from miniapp_catalog import miniapp_toggle_ad_channel
from miniapp_catalog import miniapp_update_team
from miniapp_catalog import miniapp_update_venue
from miniapp_core import miniapp_audit_log
from miniapp_core import miniapp_me
from miniapp_media import miniapp_access_users
from miniapp_media import miniapp_create_access_invite
from miniapp_media import miniapp_options
from miniapp_media import miniapp_poster
from miniapp_media import miniapp_update_access_user
from miniapp_media import miniapp_upload_poster
from miniapp_promotion import miniapp_announcement_preview
from miniapp_promotion import miniapp_cancel_show
from miniapp_promotion import miniapp_clone_show
from miniapp_promotion import miniapp_promotion
from miniapp_promotion import miniapp_publish
from miniapp_promotion import miniapp_send_test_announcement
from miniapp_promotion import miniapp_show_qr
from miniapp_security import MiniAppRateLimiter
from miniapp_security import miniapp_auth_concurrency_middleware
from miniapp_security import miniapp_auth_middleware
from miniapp_security import miniapp_rate_limit_middleware
from miniapp_security import miniapp_request_logging_middleware
from miniapp_security import miniapp_security_headers_middleware
from miniapp_show_write import miniapp_create_show
from miniapp_show_write import miniapp_update_show
from miniapp_shows import miniapp_attention
from miniapp_shows import miniapp_show_detail
from miniapp_shows import miniapp_shows
from miniapp_tasks_chat import miniapp_clear_registration_chat
from miniapp_tasks_chat import miniapp_confirm_manual_notifications
from miniapp_tasks_chat import miniapp_delete_show
from miniapp_tasks_chat import miniapp_registration_chat
from miniapp_tasks_chat import miniapp_registration_chats
from miniapp_tasks_chat import miniapp_remind_viewers
from miniapp_tasks_chat import miniapp_restore_show
from miniapp_tasks_chat import miniapp_show_tasks
from miniapp_tasks_chat import miniapp_verify_registration_chat

async def miniapp_index(request: web.Request) -> web.FileResponse:
    index = MINIAPP_DIST / "index.html"
    if not index.is_file():
        raise web.HTTPServiceUnavailable(text="Mini App frontend is not built")
    return web.FileResponse(index)


def register_miniapp_routes(app: web.Application) -> None:
    app[MINIAPP_RATE_LIMITER_KEY] = MiniAppRateLimiter()
    app[MINIAPP_AUTH_CONCURRENCY_KEY] = asyncio.Semaphore(settings.MAX_CONCURRENT_MINIAPP_AUTH)
    app[MINIAPP_CONCURRENCY_KEY] = asyncio.Semaphore(settings.MAX_CONCURRENT_MINIAPP_REQUESTS)
    app[MINIAPP_UPLOAD_CONCURRENCY_KEY] = asyncio.Semaphore(settings.MAX_CONCURRENT_POSTER_UPLOADS)
    app.middlewares.append(miniapp_security_headers_middleware)
    app.middlewares.append(miniapp_request_logging_middleware)
    app.middlewares.append(miniapp_auth_concurrency_middleware)
    app.middlewares.append(miniapp_auth_middleware)
    app.middlewares.append(miniapp_rate_limit_middleware)
    app.router.add_get("/api/miniapp/me", miniapp_me)
    app.router.add_get("/api/miniapp/shows", miniapp_shows)
    app.router.add_post("/api/miniapp/shows", miniapp_create_show)
    app.router.add_get("/api/miniapp/shows/{show_id}", miniapp_show_detail)
    app.router.add_patch("/api/miniapp/shows/{show_id}", miniapp_update_show)
    app.router.add_delete("/api/miniapp/shows/{show_id}", miniapp_delete_show)
    app.router.add_post("/api/miniapp/shows/{show_id}/restore", miniapp_restore_show)
    app.router.add_get("/api/miniapp/options", miniapp_options)
    app.router.add_get("/api/miniapp/access/users", miniapp_access_users)
    app.router.add_get("/api/miniapp/audit-log", miniapp_audit_log)
    app.router.add_post("/api/miniapp/access/invites", miniapp_create_access_invite)
    app.router.add_patch("/api/miniapp/access/users/{user_id}", miniapp_update_access_user)
    app.router.add_post("/api/miniapp/teams", miniapp_create_team)
    app.router.add_patch("/api/miniapp/teams/{team_id}", miniapp_update_team)
    app.router.add_delete("/api/miniapp/teams/{team_id}", miniapp_delete_team)
    app.router.add_post("/api/miniapp/venues", miniapp_create_venue)
    app.router.add_patch("/api/miniapp/venues/{venue_id}", miniapp_update_venue)
    app.router.add_delete("/api/miniapp/venues/{venue_id}", miniapp_delete_venue)
    app.router.add_post("/api/miniapp/ad-channels", miniapp_create_ad_channel)
    app.router.add_patch("/api/miniapp/ad-channels/{channel_id}/toggle", miniapp_toggle_ad_channel)
    app.router.add_delete("/api/miniapp/ad-channels/{channel_id}", miniapp_delete_ad_channel)
    app.router.add_get("/api/miniapp/shows/{show_id}/attendees", miniapp_attendees)
    app.router.add_post("/api/miniapp/shows/{show_id}/attendees/manual", miniapp_add_manual_attendee)
    app.router.add_get("/api/miniapp/attention", miniapp_attention)
    app.router.add_get("/api/miniapp/shows/{show_id}/tasks", miniapp_show_tasks)
    app.router.add_post("/api/miniapp/shows/{show_id}/remind", miniapp_remind_viewers)
    app.router.add_put("/api/miniapp/shows/{show_id}/registration-chat", miniapp_registration_chat)
    app.router.add_delete("/api/miniapp/shows/{show_id}/registration-chat", miniapp_clear_registration_chat)
    app.router.add_get("/api/miniapp/registration-chats", miniapp_registration_chats)
    app.router.add_post("/api/miniapp/registration-chat/verify", miniapp_verify_registration_chat)
    app.router.add_post("/api/miniapp/shows/{show_id}/manual-notifications/confirm", miniapp_confirm_manual_notifications)
    app.router.add_patch("/api/miniapp/shows/{show_id}/registrations/{registration_id}", miniapp_update_registration)
    app.router.add_delete("/api/miniapp/shows/{show_id}/registrations/{registration_id}", miniapp_cancel_registration)
    app.router.add_get("/api/miniapp/shows/{show_id}/announcement-preview", miniapp_announcement_preview)
    app.router.add_get("/api/miniapp/shows/{show_id}/promotion", miniapp_promotion)
    app.router.add_post("/api/miniapp/shows/{show_id}/promotion/test", miniapp_send_test_announcement)
    app.router.add_post("/api/miniapp/shows/{show_id}/publish", miniapp_publish)
    app.router.add_post("/api/miniapp/shows/{show_id}/clone", miniapp_clone_show)
    app.router.add_post("/api/miniapp/shows/{show_id}/cancel", miniapp_cancel_show)
    app.router.add_get("/api/miniapp/shows/{show_id}/qr", miniapp_show_qr)
    app.router.add_get("/api/miniapp/shows/{show_id}/analytics", miniapp_show_analytics)
    app.router.add_get("/api/miniapp/shows/{show_id}/export.csv", miniapp_export_show_csv)
    app.router.add_post("/api/miniapp/shows/{show_id}/poster", miniapp_upload_poster)
    app.router.add_get("/api/miniapp/shows/{show_id}/poster", miniapp_poster)
    app.router.add_get("/app", miniapp_index)
    if MINIAPP_DIST.is_dir():
        app.router.add_static("/app/assets", MINIAPP_DIST / "assets", show_index=False)
