from datetime import datetime, time, timedelta, timezone

from app.config import settings


def now() -> datetime:
    """Current local time (naive). All datetimes in the DB are stored in this local time."""
    tz = timezone(timedelta(minutes=settings.TZ_OFFSET_MINUTES))
    return datetime.now(tz).replace(tzinfo=None)


def to_local_naive(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    tz = timezone(timedelta(minutes=settings.TZ_OFFSET_MINUTES))
    return dt.astimezone(tz).replace(tzinfo=None)


def is_restaurant_open(restaurant, at: datetime = None) -> bool:
    """Open only if active, not temporarily closed, and current time within opening/closing."""
    at = at or now()
    if not restaurant.is_active or restaurant.is_temporarily_closed:
        return False
    current: time = at.time().replace(microsecond=0)
    return restaurant.opening_time <= current < restaurant.closing_time
