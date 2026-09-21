"""Search predicates independent of the UI and the translated date labels."""
import calendar
from datetime import datetime, timedelta


DATE_FILTER_LABELS = (
    "كل التواريخ", "منذ يوم", "منذ أسبوع", "منذ شهر", "منذ 6 أشهر",
    "منذ عام", "منذ عامين", "منذ 3 أعوام", "منذ أكثر من 5 أعوام",
)


def date_cutoff(selection: int, now: datetime | None = None) -> float | None:
    now = now or datetime.now().astimezone()
    if selection == 0:
        return None
    if selection in (1, 2):
        return (now - timedelta(days=1 if selection == 1 else 7)).timestamp()
    months = {3: 1, 4: 6, 5: 12, 6: 24, 7: 36, 8: 60}[selection]
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    month += 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day).timestamp()


def matches_filters(message, sender: str = "", cutoff: float | None = None, *, older_than: bool = False, now: float | None = None) -> bool:
    haystack = f"{message.sender} {message.sender_email}".casefold()
    if not all(term in haystack for term in sender.casefold().split()):
        return False
    if cutoff is None:
        return True
    timestamp = message.sort_timestamp
    if older_than:
        return 0 < timestamp < cutoff
    upper = datetime.now().timestamp() if now is None else now
    return 0 < timestamp and cutoff <= timestamp <= upper
