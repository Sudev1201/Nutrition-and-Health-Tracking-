"""The user's date and wall clock. A day boundary is theirs, not the server's."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown name, or one malformed enough to be rejected outright. A bad
        # stored timezone should not break the request; UTC is a defensible last
        # resort, and clients pass dates explicitly for most reads anyway.
        return ZoneInfo("UTC")


def local_today(user: User) -> datetime.date:
    return datetime.datetime.now(tz=_zone(user)).date()


def local_now(user: User, now_utc: datetime.datetime) -> datetime.datetime:
    """The instant `now_utc` on the user's wall clock: aware, in their zone.

    It takes the instant rather than reading the clock, so one reminder tick
    decides every user at the same moment, and its tests can choose that moment.
    """
    if now_utc.tzinfo is None:
        # astimezone() would read a naive value as the server's own local time.
        raise ValueError("now_utc must be timezone-aware")
    return now_utc.astimezone(_zone(user))
