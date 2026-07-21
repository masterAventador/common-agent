from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from common_agent.api.authentication import (
    authenticate_request,
    authentication_error_to_app_error,
    require_authenticated,
)
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.auth import (
    AuthenticatedSession,
    AuthenticationError,
    AuthenticationService,
    IssuedAuthentication,
    PasswordPolicyError,
)
from common_agent.bootstrap import AuthSettings

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class AuthPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registration_available: bool


class RegisterBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[SecretStr, Field(min_length=15, max_length=128)]
    bootstrap_token: Annotated[SecretStr, Field(min_length=1, max_length=256)]


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=128)]


class RecoveryResetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=3, max_length=254)]
    recovery_code: Annotated[SecretStr, Field(min_length=17, max_length=17)]
    new_password: Annotated[SecretStr, Field(min_length=15, max_length=128)]


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    csrf_token: str
    idle_expires_at: datetime
    absolute_expires_at: datetime


class RegistrationResponse(AuthSessionResponse):
    recovery_codes: tuple[str, ...]


@router.get("/policy", response_model=AuthPolicyResponse)
async def policy(request: Request) -> AuthPolicyResponse:
    registration_available = await _service(request).registration_available()
    return AuthPolicyResponse(registration_available=registration_available)


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegistrationResponse,
    responses={403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def register(
    body: RegisterBody,
    request: Request,
    response: Response,
) -> RegistrationResponse:
    try:
        issued = await _service(request).register_owner(
            email=body.email,
            password=body.password.get_secret_value(),
            bootstrap_token=body.bootstrap_token.get_secret_value(),
        )
    except (AuthenticationError, PasswordPolicyError) as error:
        raise _request_error(error) from error
    _set_session_cookie(response, request, issued)
    _no_store(response)
    return RegistrationResponse(
        user_id=UUID(issued.user_id),
        email=issued.email,
        csrf_token=issued.csrf_token,
        idle_expires_at=issued.idle_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
        recovery_codes=issued.recovery_codes,
    )


@router.post(
    "/login",
    response_model=AuthSessionResponse,
    responses={401: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
)
async def login(body: LoginBody, request: Request, response: Response) -> AuthSessionResponse:
    try:
        issued = await _service(request).login(
            email=body.email,
            password=body.password.get_secret_value(),
            client_address=_client_address(request),
        )
    except AuthenticationError as error:
        raise authentication_error_to_app_error(error) from error
    _set_session_cookie(response, request, issued)
    _no_store(response)
    return _issued_session_response(issued)


@router.get(
    "/session",
    response_model=AuthSessionResponse,
    dependencies=[Depends(require_authenticated)],
    responses={401: {"model": ErrorEnvelope}},
)
async def current_session(request: Request, response: Response) -> AuthSessionResponse:
    session = await authenticate_request(request)
    _no_store(response)
    return _session_response(session)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_authenticated)],
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def logout(request: Request, response: Response) -> None:
    session_token = getattr(request.state, "auth_session_token", "")
    await _service(request).logout(session_token)
    settings = _settings(request)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    _no_store(response)


@router.post(
    "/recovery/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorEnvelope}, 429: {"model": ErrorEnvelope}},
)
async def reset_password(body: RecoveryResetBody, request: Request, response: Response) -> None:
    try:
        await _service(request).reset_password(
            email=body.email,
            recovery_code=body.recovery_code.get_secret_value(),
            new_password=body.new_password.get_secret_value(),
            client_address=_client_address(request),
        )
    except (AuthenticationError, PasswordPolicyError) as error:
        raise _request_error(error) from error
    _no_store(response)


def _service(request: Request) -> AuthenticationService:
    service = getattr(request.app.state, "authentication", None)
    if not isinstance(service, AuthenticationService):
        raise AppError("authentication_unavailable", "认证服务暂时不可用", 503, True)
    return service


def _settings(request: Request) -> AuthSettings:
    settings = getattr(request.app.state, "auth_settings", None)
    if not isinstance(settings, AuthSettings):
        raise AppError("authentication_unavailable", "认证服务暂时不可用", 503, True)
    return settings


def _set_session_cookie(
    response: Response,
    request: Request,
    issued: IssuedAuthentication,
) -> None:
    settings = _settings(request)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=issued.session_token,
        max_age=settings.session_absolute_seconds,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _issued_session_response(issued: IssuedAuthentication) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=UUID(issued.user_id),
        email=issued.email,
        csrf_token=issued.csrf_token,
        idle_expires_at=issued.idle_expires_at,
        absolute_expires_at=issued.absolute_expires_at,
    )


def _session_response(session: AuthenticatedSession) -> AuthSessionResponse:
    return AuthSessionResponse(
        user_id=UUID(session.user_id),
        email=session.email,
        csrf_token=session.csrf_token,
        idle_expires_at=session.idle_expires_at,
        absolute_expires_at=session.absolute_expires_at,
    )


def _request_error(error: AuthenticationError | PasswordPolicyError) -> AppError:
    if isinstance(error, AuthenticationError):
        return authentication_error_to_app_error(error)
    return AppError("validation_error", "请求参数不合法", 422, False)


def _client_address(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
