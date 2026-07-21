from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from fastapi import Request, Response

from common_agent.api.errors import AppError, app_error_handler
from common_agent.auth import AuthenticatedSession, AuthenticationError, AuthenticationService
from common_agent.bootstrap import AuthSettings, CorsSettings

RequestHandler = Callable[[Request], Awaitable[Response]]
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_PUBLIC_AUTH_WRITES = frozenset(
    {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/recovery/reset",
    }
)


async def enforce_request_security(request: Request, call_next: RequestHandler) -> Response:
    if request.method in _SAFE_METHODS or not request.url.path.startswith("/api/v1/"):
        return await call_next(request)

    try:
        if request.url.path in _PUBLIC_AUTH_WRITES:
            _require_trusted_origin(request)
            _require_json(request)
        else:
            session = await authenticate_request(request)
            _require_trusted_origin(request)
            csrf_token = request.headers.get("X-CSRF-Token", "")
            if not _authentication_service(request).csrf_matches(session, csrf_token):
                raise AppError(
                    code="csrf_validation_failed",
                    message="请求安全校验失败",
                    status_code=403,
                    retryable=False,
                )
    except AppError as error:
        return await app_error_handler(request, error)

    response = await call_next(request)
    response.headers.append("Vary", "Origin, Sec-Fetch-Site")
    return response


async def require_authenticated(request: Request) -> AuthenticatedSession:
    return await authenticate_request(request)


async def authenticate_request(request: Request) -> AuthenticatedSession:
    cached = getattr(request.state, "authenticated_session", None)
    if isinstance(cached, AuthenticatedSession):
        return cached

    settings = _auth_settings(request)
    session_token = request.cookies.get(settings.session_cookie_name, "")
    try:
        session = await _authentication_service(request).authenticate(session_token)
    except AuthenticationError as error:
        raise authentication_error_to_app_error(error) from error
    request.state.authenticated_session = session
    request.state.auth_session_token = session_token
    return session


def authentication_error_to_app_error(error: AuthenticationError) -> AppError:
    mapping: dict[str, tuple[str, int, bool]] = {
        "authentication_required": ("请先登录", 401, False),
        "invalid_credentials": ("邮箱或密码不正确", 401, False),
        "login_rate_limited": ("登录尝试过多，请稍后重试", 429, True),  # noqa: RUF001
        "recovery_rate_limited": ("恢复尝试过多，请稍后重试", 429, True),  # noqa: RUF001
        "invalid_recovery_credentials": ("恢复凭据无效", 401, False),
        "invalid_bootstrap_token": ("站点引导凭据无效", 403, False),
        "registration_unavailable": ("站点注册已关闭", 409, False),
        "invalid_email": ("请求参数不合法", 422, False),
    }
    message, status_code, retryable = mapping.get(
        error.code,
        ("认证请求失败", 401, False),
    )
    return AppError(
        code=error.code,
        message=message,
        status_code=status_code,
        retryable=retryable,
    )


def _require_trusted_origin(request: Request) -> None:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
    if fetch_site == "cross-site":
        _raise_origin_error()

    source = request.headers.get("Origin")
    if source is None:
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlparse(referer)
            source = f"{parsed.scheme}://{parsed.netloc}"
    if source is None or source.rstrip("/") not in _cors_settings(request).origins:
        _raise_origin_error()


def _raise_origin_error() -> None:
    raise AppError(
        code="origin_validation_failed",
        message="请求来源不受信任",
        status_code=403,
        retryable=False,
    )


def _require_json(request: Request) -> None:
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise AppError(
            code="unsupported_media_type",
            message="认证请求必须使用 JSON",
            status_code=415,
            retryable=False,
        )


def _authentication_service(request: Request) -> AuthenticationService:
    service = getattr(request.app.state, "authentication", None)
    if not isinstance(service, AuthenticationService):
        raise AppError(
            code="authentication_unavailable",
            message="认证服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return service


def _auth_settings(request: Request) -> AuthSettings:
    settings = getattr(request.app.state, "auth_settings", None)
    if not isinstance(settings, AuthSettings):
        raise RuntimeError("auth settings are not configured")
    return settings


def _cors_settings(request: Request) -> CorsSettings:
    settings = getattr(request.app.state, "cors_settings", None)
    if not isinstance(settings, CorsSettings):
        raise RuntimeError("cors settings are not configured")
    return settings
