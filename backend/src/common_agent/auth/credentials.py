from __future__ import annotations

import hashlib
import secrets

PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128
RECOVERY_CODE_COUNT = 8
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PasswordPolicyError(ValueError):
    """Raised when a password does not meet the platform length policy."""


def validate_password(password: str) -> str:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(
            f"password length must be between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH}"
        )
    return password


def create_session_token() -> str:
    return secrets.token_urlsafe(32)


def create_recovery_codes() -> tuple[str, ...]:
    return tuple(f"{_recovery_segment()}-{_recovery_segment()}" for _ in range(RECOVERY_CODE_COUNT))


def digest_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _recovery_segment() -> str:
    return "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
