"""Calendar arithmetic shared by paid assignment entry points."""
from calendar import monthrange
from datetime import datetime
from zoneinfo import ZoneInfo


def add_calendar_months(value: datetime, months: int) -> datetime:
    """Add Shanghai calendar months, clipping the day to the destination month."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware datetime required')
    local = value.astimezone(ZoneInfo('Asia/Shanghai'))
    year, month = divmod(local.year * 12 + local.month - 1 + months, 12)
    month += 1
    return local.replace(year=year, month=month,
                         day=min(local.day, monthrange(year, month)[1]))
