from __future__ import annotations
from miniapp_common import *


@web.middleware
async def miniapp_auth_concurrency_middleware(request: web.Request, handler):
    """Bound signature checks and database lookups before per-user limiting."""
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    semaphore = request.app[MINIAPP_AUTH_CONCURRENCY_KEY]
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=0.5)
    except asyncio.TimeoutError:
        raise web.HTTPServiceUnavailable(
            text=json.dumps({"error": "authentication_capacity_exceeded"}),
            content_type="application/json",
            headers={"Retry-After": "1"},
        )
    try:
        return await handler(request)
    finally:
        semaphore.release()


class MiniAppRateLimiter:
    """Small per-process sliding-window limiter keyed by authenticated user."""

    def __init__(self) -> None:
        self._events: dict[tuple[int, str], deque[float]] = defaultdict(deque)
        self._last_cleanup = 0.0

    def allow(
        self, user_id: int, bucket: str, limit: int, window: float, *, now: float,
    ) -> tuple[bool, int]:
        if now - self._last_cleanup >= 300:
            stale_before = now - 60
            for key, recorded in list(self._events.items()):
                while recorded and recorded[0] <= stale_before:
                    recorded.popleft()
                if not recorded:
                    self._events.pop(key, None)
            self._last_cleanup = now
        events = self._events[(user_id, bucket)]
        cutoff = now - window
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= limit:
            return False, max(1, int(window - (now - events[0]) + 0.999))
        events.append(now)
        return True, 0


def _miniapp_rate_policy(request: web.Request) -> tuple[str, int, int] | None:
    path = request.path
    if request.method == "POST" and path.endswith("/poster"):
        return "poster_upload", 3, 60
    if (
        request.method == "POST"
        and (path.endswith("/publish") or path.endswith("/remind") or path.endswith("/promotion/test"))
    ):
        return "telegram_send", 5, 60
    if request.method == "GET" and path.endswith("/export.csv"):
        return "csv_export", 5, 60
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        return "mutation", 30, 60
    return None


@web.middleware
async def miniapp_rate_limit_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    user_id = request["miniapp_user_id"]
    limiter = request.app[MINIAPP_RATE_LIMITER_KEY]
    now = time.monotonic()
    policies = [("all", 120, 60)]
    specific = _miniapp_rate_policy(request)
    if specific:
        policies.append(specific)
    for bucket, limit, window in policies:
        allowed, retry_after = limiter.allow(user_id, bucket, limit, window, now=now)
        if not allowed:
            raise web.HTTPTooManyRequests(
                text=json.dumps({"error": "rate_limit_exceeded", "bucket": bucket}),
                content_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
    async with request.app[MINIAPP_CONCURRENCY_KEY]:
        if request.method == "POST" and request.path.endswith("/poster"):
            async with request.app[MINIAPP_UPLOAD_CONCURRENCY_KEY]:
                return await handler(request)
        return await handler(request)


class MiniAppAuthError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramMiniAppUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    now: int | None = None,
    max_age_seconds: int = MAX_INIT_DATA_AGE_SECONDS,
) -> TelegramMiniAppUser:
    """Validate Telegram Mini App initData according to Telegram's HMAC scheme."""
    if not init_data or len(init_data) > 8192:
        raise MiniAppAuthError("missing or oversized init data")

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise MiniAppAuthError("malformed init data") from exc
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise MiniAppAuthError("duplicate init data field")
        fields[key] = value

    supplied_hash = fields.pop("hash", "")
    if len(supplied_hash) != 64:
        raise MiniAppAuthError("invalid init data hash")
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied_hash, expected_hash):
        raise MiniAppAuthError("invalid init data signature")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MiniAppAuthError("invalid auth date") from exc
    current_time = int(time.time()) if now is None else now
    if auth_date > current_time + 30 or current_time - auth_date > max_age_seconds:
        raise MiniAppAuthError("expired init data")

    try:
        telegram_user = json.loads(fields["user"])
        if not isinstance(telegram_user, dict):
            raise TypeError
        telegram_id = int(telegram_user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MiniAppAuthError("invalid Telegram user") from exc
    if telegram_id <= 0:
        raise MiniAppAuthError("invalid Telegram user id")
    return TelegramMiniAppUser(
        telegram_id=telegram_id,
        username=telegram_user.get("username"),
        first_name=telegram_user.get("first_name"),
        last_name=telegram_user.get("last_name"),
    )


def _extract_init_data(request: web.Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("tma "):
        return authorization[4:]
    return request.headers.get("X-Telegram-Init-Data", "")


@web.middleware
async def miniapp_auth_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    init_data = _extract_init_data(request)
    try:
        telegram_user = validate_telegram_init_data(
            init_data, settings.ADMIN_BOT_TOKEN,
        )
    except MiniAppAuthError as exc:
        logger.warning(
            "Mini App authentication rejected request_id=%s path=%s reason=%s init_data_present=%s",
            request.get("miniapp_request_id", "unknown"), request.path, exc, bool(init_data),
        )
        raise web.HTTPUnauthorized(
            text=json.dumps({"error": "telegram_auth_failed"}),
            content_type="application/json",
        )

    async with AsyncSessionLocal() as session:
        db_user = await session.scalar(
            select(User).where(User.telegram_id == telegram_user.telegram_id)
        )
        if db_user is None or db_user.role not in (UserRole.organizer, UserRole.admin):
            raise web.HTTPForbidden(
                text=json.dumps({"error": "organizer_access_required"}),
                content_type="application/json",
            )
        request["miniapp_user_id"] = db_user.id
        request["miniapp_telegram_id"] = telegram_user.telegram_id
        request["miniapp_is_super_admin"] = telegram_user.telegram_id in ADMIN_ID_LIST
        request["miniapp_is_admin"] = (
            db_user.role == UserRole.admin or telegram_user.telegram_id in ADMIN_ID_LIST
        )
    return await handler(request)


@web.middleware
async def miniapp_request_logging_middleware(request: web.Request, handler):
    if not request.path.startswith("/api/miniapp/"):
        return await handler(request)
    request_id = secrets.token_hex(6)
    request["miniapp_request_id"] = request_id
    started_at = time.monotonic()
    status = 500
    try:
        response = await handler(request)
        status = response.status
        response.headers["X-Request-ID"] = request_id
        return response
    except web.HTTPException as exc:
        status = exc.status
        exc.headers["X-Request-ID"] = request_id
        raise
    except Exception:
        logger.exception(
            "Mini App request failed request_id=%s method=%s path=%s user_id=%s telegram_id=%s",
            request_id, request.method, request.path,
            request.get("miniapp_user_id"), request.get("miniapp_telegram_id"),
        )
        response = web.json_response(
            {"error": "internal_error", "requestId": request_id}, status=500,
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        duration_ms = (time.monotonic() - started_at) * 1000
        log = logger.warning if status >= 400 else logger.info
        log(
            "Mini App request completed request_id=%s method=%s path=%s status=%s "
            "duration_ms=%.1f user_id=%s telegram_id=%s",
            request_id, request.method, request.path, status, duration_ms,
            request.get("miniapp_user_id"), request.get("miniapp_telegram_id"),
        )


@web.middleware
async def miniapp_security_headers_middleware(request: web.Request, handler):
    try:
        response = await handler(request)
    except web.HTTPException as response:
        _set_miniapp_security_headers(request, response)
        raise
    _set_miniapp_security_headers(request, response)
    return response


def _set_miniapp_security_headers(request: web.Request, response: web.StreamResponse) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains",
    )
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()",
    )
    if request.path.startswith("/api/miniapp/"):
        response.headers.setdefault("Cache-Control", "private, no-store")
    elif request.path == "/app" or request.path.startswith("/app/"):
        if request.path.startswith("/app/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        else:
            response.headers.setdefault("Cache-Control", "no-store, max-age=0, must-revalidate")
            response.headers.setdefault("Pragma", "no-cache")
            response.headers.setdefault("Expires", "0")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
            "connect-src 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org; "
            "object-src 'none'; base-uri 'none'; form-action 'self'; upgrade-insecure-requests",
        )
