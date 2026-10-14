"""Department worklists (lab, Scancare, pharmacy, ...) work like Queue & Flow: the main list is what is still to do
(any day - unfinished work never drops off), and "Done today" lists what was finished since midnight Lagos time, so
every morning that section starts empty."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

LAGOS = ZoneInfo("Africa/Lagos")


def today_start_utc() -> str:
    """Midnight today in Lagos, as a UTC ISO timestamp for >= filters."""
    return datetime.combine(datetime.now(LAGOS).date(), time.min, LAGOS).astimezone(timezone.utc).isoformat()


def apply_view(query, view, active_statuses, done_statuses, done_at_column):
    """view=active: unfinished, any date. view=done: finished since midnight. Anything else: unchanged."""
    if view == "active":
        return query.in_("status", sorted(active_statuses))
    if view == "done":
        return query.in_("status", sorted(done_statuses)).gte(done_at_column, today_start_utc())
    return query
