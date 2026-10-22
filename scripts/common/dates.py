"""Edition-local report dates and the shared 05:00 daily window."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _date(value: date | datetime | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(value) if isinstance(value, str) else value


def _zone(value: str | ZoneInfo) -> ZoneInfo:
    return ZoneInfo(value) if isinstance(value, str) else value


def subject(name: str, report_date: date | datetime | str, tail: str) -> str:
    """Build a locale-independent human date while retaining the metric tail."""
    day = _date(report_date)
    stamp = f"{DAYS[day.weekday()][:3]}, {SHORT_MONTHS[day.month - 1]} {day.day}"
    return f"{name} · {stamp} — {tail}"


def report_date_for(now: datetime, tz: str | ZoneInfo) -> date:
    """Most recent report whose 05:00 edition-local cutoff has passed.

    This is the manual-run default. Scheduled gates select their next morning
    with catchup_gate.plan, then carry that explicit report date through send.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    local = now.astimezone(_zone(tz))
    return local.date() if local.time() >= time(5) else local.date() - timedelta(days=1)


def window_for(report_date: date | datetime | str, tz: str | ZoneInfo) -> tuple[datetime, datetime]:
    """Return [05:00 D-1, 05:00 D), preserving local wall time across DST.

    Callers must include records at start and exclude records at end. The UTC
    elapsed duration can be 23 or 25 hours across Pacific DST transitions.
    """
    day, zone = _date(report_date), _zone(tz)
    return (datetime.combine(day - timedelta(days=1), time(5), zone),
            datetime.combine(day, time(5), zone))


def long_date(value: date | datetime | str) -> str:
    day = _date(value)
    return f"{DAYS[day.weekday()]}, {day.day} {MONTHS[day.month - 1]} {day.year}"
