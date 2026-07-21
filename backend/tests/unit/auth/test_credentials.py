from __future__ import annotations

import re

import pytest

from common_agent.adapters.auth.passwords import Argon2PasswordHasher
from common_agent.auth.credentials import (
    PasswordPolicyError,
    create_recovery_codes,
    create_session_token,
    digest_secret,
    validate_password,
)


def test_passwords_use_argon2id_and_verify_without_retaining_plaintext() -> None:
    hasher = Argon2PasswordHasher()
    password = "correct horse battery staple"

    encoded = hasher.hash(password)

    assert encoded.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert password not in encoded
    assert hasher.verify(password, encoded) is True
    assert hasher.verify("wrong password value", encoded) is False


@pytest.mark.parametrize(
    "password",
    [
        "x" * 7,
        "x" * 129,
    ],
)
def test_password_policy_rejects_only_unsafe_length_boundaries(password: str) -> None:
    with pytest.raises(PasswordPolicyError):
        validate_password(password)


def test_password_policy_accepts_eight_character_minimum() -> None:
    assert validate_password("Owner#28") == "Owner#28"


def test_password_policy_accepts_long_unicode_passphrases_without_normalizing_them() -> None:
    password = " 这是我唯一且足够长的登录口令 🔐 "

    assert validate_password(password) == password


def test_session_and_recovery_credentials_are_random_url_safe_and_only_digest_persists() -> None:
    session_tokens = {create_session_token() for _ in range(32)}
    recovery_codes = create_recovery_codes()

    assert len(session_tokens) == 32
    assert all(re.fullmatch(r"[A-Za-z0-9_-]{43}", token) for token in session_tokens)
    assert len(recovery_codes) == 8
    assert len(set(recovery_codes)) == 8
    assert all(re.fullmatch(r"[A-Z2-9]{8}-[A-Z2-9]{8}", code) for code in recovery_codes)
    assert all(code not in digest_secret(code) for code in recovery_codes)
    assert all(len(digest_secret(code)) == 64 for code in recovery_codes)
