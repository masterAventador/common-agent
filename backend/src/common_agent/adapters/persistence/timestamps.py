from datetime import UTC, datetime


def to_database_datetime(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def from_database_datetime(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)
