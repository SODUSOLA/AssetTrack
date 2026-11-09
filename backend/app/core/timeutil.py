"""Time handling: store UTC, interpret calendar dates in Africa/Lagos (SPEC 1.5)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Africa/Lagos")


def utcnow() -> datetime:
    return datetime.now(UTC)


def lagos_day_start(day: date) -> datetime:
    """00:00 Lagos time on `day`, as an aware datetime."""
    return datetime.combine(day, time.min, tzinfo=APP_TIMEZONE)


def lagos_range(
    date_from: date | None, date_to: date | None
) -> tuple[datetime | None, datetime | None]:
    """Half-open [start, end) UTC-comparable bounds for inclusive Lagos calendar dates."""
    start = lagos_day_start(date_from) if date_from else None
    end = lagos_day_start(date_to + timedelta(days=1)) if date_to else None
    return start, end


def lagos_today() -> date:
    return utcnow().astimezone(APP_TIMEZONE).date()


def lagos_iso(value: datetime) -> str:
    """Local wall-clock time with its offset, to the minute: 2026-10-05T14:30+01:00."""
    return value.astimezone(APP_TIMEZONE).isoformat(timespec="minutes")


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    """Half-open [start, end) of a calendar month in Africa/Lagos, as aware datetimes."""
    first = date(year, month, 1)
    following = date(year + (month == 12), month % 12 + 1, 1)
    return lagos_day_start(first), lagos_day_start(following)
