from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def local_date(dt: datetime) -> date:
    """The DISPLAY_TZ calendar date of a UTC instant (naive values are taken as UTC). docs/03 §6.4.

    Use it for every value that is a date rather than a timestamp: a call at 23:30 ET on Oct 10 is
    2026-10-11T03:30Z, and its date is Oct 10, not the UTC date Oct 11.
    """
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
    return aware.astimezone(ZoneInfo(get_settings().display_tz)).date()
