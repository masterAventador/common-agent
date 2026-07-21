from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuthConfiguration:
    bootstrap_token: str = field(repr=False)
    session_idle_seconds: int
    session_absolute_seconds: int
    login_window_seconds: int
    login_max_attempts: int


@dataclass(frozen=True, slots=True)
class StoredAuthUser:
    id: str
    email: str
    password_hash: str = field(repr=False)
    is_active: bool


@dataclass(frozen=True, slots=True)
class AuthenticatedSession:
    id: str
    user_id: str
    email: str
    csrf_token: str = field(repr=False)
    idle_expires_at: datetime
    absolute_expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedAuthentication:
    user_id: str
    email: str
    session_token: str = field(repr=False)
    csrf_token: str = field(repr=False)
    idle_expires_at: datetime
    absolute_expires_at: datetime
    recovery_codes: tuple[str, ...] = field(default=(), repr=False)
