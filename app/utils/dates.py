"""Calendar helpers."""

import calendar
import datetime as dt


def add_months(day: dt.date, months: int) -> dt.date:
    """Shift by whole months keeping the day where possible: Jan 31 + 1 month -> Feb 28/29."""
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return dt.date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))
