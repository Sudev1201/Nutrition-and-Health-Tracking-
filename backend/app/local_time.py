"""The user's calendar date. A day boundary is theirs, not the server's."""

import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


def local_today(user: User) -> datetime.date:
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        # An unknown name, or one malformed enough to be rejected outright. A bad
        # stored timezone should not break the request; UTC is a defensible last
        # resort, and clients pass dates explicitly for most reads anyway.
        zone = ZoneInfo("UTC")
    return datetime.datetime.now(tz=zone).date()
