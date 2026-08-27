"""Working-hours window for quiet mode (skip runs / stop serve off-hours)."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from status_overlook.config import WorkingHoursConfig

_WEEKDAYS: dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def _parse_clock(value: str) -> time:
    text = (value or "").strip()
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"invalid time {value!r} (expected HH:MM)")
    hour = int(parts[0])
    minute = int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"invalid time {value!r}")
    return time(hour, minute)


def _weekday_set(days: tuple[str, ...]) -> set[int]:
    out: set[int] = set()
    for day in days:
        key = day.strip().casefold()
        if key in _WEEKDAYS:
            out.add(_WEEKDAYS[key])
    return out


def _resolve_tz(timezone: str):
    tz_name = (timezone or "").strip()
    if tz_name:
        return ZoneInfo(tz_name)
    return datetime.now().astimezone().tzinfo


def is_within_working_hours(
    wh: WorkingHoursConfig,
    *,
    now: datetime | None = None,
) -> bool:
    """Return True when runs/serve are allowed (disabled config always True)."""
    if not wh.enabled:
        return True

    tz = _resolve_tz(wh.timezone)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    else:
        now = now.astimezone(tz)

    allowed_days = _weekday_set(wh.days)
    if now.weekday() not in allowed_days:
        return False

    start = _parse_clock(wh.start)
    end = _parse_clock(wh.end)
    current = now.time()
    return start <= current < end
