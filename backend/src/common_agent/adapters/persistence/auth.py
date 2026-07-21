from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    AuthLoginAttemptRow,
    AuthRecoveryCodeRow,
    AuthSessionRow,
    AuthUserRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.auth.models import AuthenticatedSession, StoredAuthUser


class SqlAlchemyAuthStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def registration_available(self) -> bool:
        async with self._database.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(AuthUserRow)
                .where(AuthUserRow.bootstrap_slot == "owner")
            )
            return int(result.scalar_one()) == 0

    async def create_owner(
        self,
        *,
        email: str,
        password_hash: str,
        recovery_digests: tuple[str, ...],
        now: datetime,
    ) -> StoredAuthUser | None:
        database_now = to_database_datetime(now)
        row = AuthUserRow(
            id=str(uuid4()),
            email=email,
            password_hash=password_hash,
            is_active=True,
            bootstrap_slot="owner",
            password_changed_at=database_now,
            created_at=database_now,
            updated_at=database_now,
        )
        try:
            async with self._database.session() as session:
                session.add(row)
                await session.flush()
                session.add_all(
                    AuthRecoveryCodeRow(
                        user_id=row.id,
                        code_digest=digest,
                        created_at=database_now,
                        consumed_at=None,
                    )
                    for digest in recovery_digests
                )
                await session.commit()
        except IntegrityError as error:
            if _mysql_error_code(error) == 1062:
                return None
            raise
        return _stored_user(row)

    async def find_user_by_email(self, email: str) -> StoredAuthUser | None:
        async with self._database.session() as session:
            result = await session.execute(select(AuthUserRow).where(AuthUserRow.email == email))
            row = result.scalar_one_or_none()
            return _stored_user(row) if row is not None else None

    async def replace_password_hash(self, user_id: str, password_hash: str) -> None:
        now = to_database_datetime(datetime.now(UTC))
        async with self._database.session() as session:
            await session.execute(
                update(AuthUserRow)
                .where(AuthUserRow.id == user_id)
                .values(
                    password_hash=password_hash,
                    password_changed_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

    async def create_session(
        self,
        *,
        user: StoredAuthUser,
        session_id: str,
        token_digest: str,
        csrf_token: str,
        now: datetime,
        idle_expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> AuthenticatedSession:
        row = AuthSessionRow(
            id=session_id,
            user_id=user.id,
            token_digest=token_digest,
            csrf_token=csrf_token,
            created_at=to_database_datetime(now),
            last_seen_at=to_database_datetime(now),
            idle_expires_at=to_database_datetime(idle_expires_at),
            absolute_expires_at=to_database_datetime(absolute_expires_at),
            revoked_at=None,
        )
        async with self._database.session() as session:
            session.add(row)
            await session.commit()
        return _authenticated_session(row, user)

    async def find_active_session(
        self,
        token_digest: str,
        *,
        now: datetime,
        idle_seconds: int,
    ) -> AuthenticatedSession | None:
        database_now = to_database_datetime(now)
        async with self._database.session() as session:
            result = await session.execute(
                select(AuthSessionRow, AuthUserRow)
                .join(AuthUserRow, AuthUserRow.id == AuthSessionRow.user_id)
                .where(AuthSessionRow.token_digest == token_digest)
                .with_for_update()
            )
            pair = result.one_or_none()
            if pair is None:
                return None
            row, user_row = pair
            if (
                not user_row.is_active
                or row.revoked_at is not None
                or database_now >= row.idle_expires_at
                or database_now >= row.absolute_expires_at
            ):
                if row.revoked_at is None:
                    row.revoked_at = database_now
                    await session.commit()
                return None

            row.last_seen_at = database_now
            row.idle_expires_at = min(
                database_now + timedelta(seconds=idle_seconds),
                row.absolute_expires_at,
            )
            await session.commit()
            return _authenticated_session(row, _stored_user(user_row))

    async def revoke_session(self, token_digest: str, *, now: datetime) -> None:
        async with self._database.session() as session:
            await session.execute(
                update(AuthSessionRow)
                .where(
                    AuthSessionRow.token_digest == token_digest,
                    AuthSessionRow.revoked_at.is_(None),
                )
                .values(revoked_at=to_database_datetime(now))
            )
            await session.commit()

    async def is_login_blocked(self, keys: tuple[str, ...], *, now: datetime) -> bool:
        async with self._database.session() as session:
            result = await session.execute(
                select(func.count())
                .select_from(AuthLoginAttemptRow)
                .where(
                    AuthLoginAttemptRow.key_digest.in_(keys),
                    AuthLoginAttemptRow.locked_until > to_database_datetime(now),
                )
            )
            return int(result.scalar_one()) > 0

    async def record_login_failure(
        self,
        keys: tuple[str, ...],
        *,
        now: datetime,
        window_seconds: int,
        max_attempts: int,
    ) -> None:
        database_now = to_database_datetime(now)
        cutoff = database_now - timedelta(seconds=window_seconds)
        locked_until = database_now + timedelta(seconds=window_seconds)
        reset_window = AuthLoginAttemptRow.window_started_at <= cutoff
        next_count = case(
            (reset_window, 1),
            else_=AuthLoginAttemptRow.failure_count + 1,
        )
        statement = mysql_insert(AuthLoginAttemptRow).values(
            [
                {
                    "key_digest": key,
                    "failure_count": 1,
                    "window_started_at": database_now,
                    "locked_until": None,
                    "updated_at": database_now,
                }
                for key in keys
            ]
        )
        statement = statement.on_duplicate_key_update(
            [
                (
                    "locked_until",
                    case(
                        (next_count >= max_attempts, locked_until),
                        else_=None,
                    ),
                ),
                ("failure_count", next_count),
                (
                    "window_started_at",
                    case(
                        (reset_window, database_now),
                        else_=AuthLoginAttemptRow.window_started_at,
                    ),
                ),
                ("updated_at", database_now),
            ]
        )
        async with self._database.session() as session:
            await session.execute(
                delete(AuthLoginAttemptRow).where(
                    AuthLoginAttemptRow.updated_at <= cutoff,
                    or_(
                        AuthLoginAttemptRow.locked_until.is_(None),
                        AuthLoginAttemptRow.locked_until <= database_now,
                    ),
                )
            )
            await session.execute(statement)
            await session.commit()

    async def clear_login_failures(self, keys: tuple[str, ...]) -> None:
        async with self._database.session() as session:
            await session.execute(
                delete(AuthLoginAttemptRow).where(AuthLoginAttemptRow.key_digest.in_(keys))
            )
            await session.commit()

    async def reset_password(
        self,
        *,
        email: str,
        recovery_digest: str,
        password_hash: str,
        now: datetime,
    ) -> bool:
        database_now = to_database_datetime(now)
        async with self._database.session() as session:
            user_result = await session.execute(
                select(AuthUserRow).where(AuthUserRow.email == email).with_for_update()
            )
            user = user_result.scalar_one_or_none()
            if user is None or not user.is_active:
                return False
            recovery_result = await session.execute(
                select(AuthRecoveryCodeRow)
                .where(
                    AuthRecoveryCodeRow.user_id == user.id,
                    AuthRecoveryCodeRow.code_digest == recovery_digest,
                    AuthRecoveryCodeRow.consumed_at.is_(None),
                )
                .with_for_update()
            )
            recovery = recovery_result.scalar_one_or_none()
            if recovery is None:
                return False

            recovery.consumed_at = database_now
            user.password_hash = password_hash
            user.password_changed_at = database_now
            user.updated_at = database_now
            await session.execute(
                update(AuthSessionRow)
                .where(
                    AuthSessionRow.user_id == user.id,
                    AuthSessionRow.revoked_at.is_(None),
                )
                .values(revoked_at=database_now)
            )
            await session.commit()
            return True


def _stored_user(row: AuthUserRow) -> StoredAuthUser:
    return StoredAuthUser(
        id=row.id,
        email=row.email,
        password_hash=row.password_hash,
        is_active=row.is_active,
    )


def _authenticated_session(
    row: AuthSessionRow,
    user: StoredAuthUser,
) -> AuthenticatedSession:
    return AuthenticatedSession(
        id=row.id,
        user_id=user.id,
        email=user.email,
        csrf_token=row.csrf_token,
        idle_expires_at=from_database_datetime(row.idle_expires_at),
        absolute_expires_at=from_database_datetime(row.absolute_expires_at),
    )


def _mysql_error_code(error: IntegrityError) -> int | None:
    arguments = getattr(error.orig, "args", ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None
