"""A user's date and wall clock are theirs, not the server's, and a garbage zone breaks neither."""

import datetime
import zoneinfo

import pytest

from app.local_time import local_now, local_today
from app.models.user import User

# 02:40 UTC is 08:10 in Kolkata, five and a half hours ahead.
INSTANT = datetime.datetime(2026, 8, 17, 2, 40, tzinfo=datetime.UTC)


def user_in(zone: str) -> User:
    return User(google_sub="s", email="e@example.com", name="n", timezone=zone)


def test_today_is_the_date_where_the_user_is():
    user = user_in("Asia/Kolkata")
    assert local_today(user) == datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()


def test_an_unknown_timezone_falls_back_to_utc():
    user = user_in("Not/AZone")
    assert local_today(user) == datetime.datetime.now(datetime.UTC).date()


def test_now_is_the_users_wall_clock():
    local = local_now(user_in("Asia/Kolkata"), INSTANT)

    assert (local.date(), local.hour, local.minute) == (datetime.date(2026, 8, 17), 8, 10)
    # The same instant, read in their zone.
    assert local == INSTANT


def test_the_users_date_can_be_a_day_ahead_of_utc():
    # 20:00 UTC on the 16th is 01:30 on the 17th in Kolkata.
    evening = datetime.datetime(2026, 8, 16, 20, 0, tzinfo=datetime.UTC)
    assert local_now(user_in("Asia/Kolkata"), evening).date() == datetime.date(2026, 8, 17)


def test_an_unknown_timezone_reads_the_clock_in_utc():
    local = local_now(user_in("Not/AZone"), INSTANT)
    assert (local.hour, local.minute, local.utcoffset()) == (2, 40, datetime.timedelta(0))


def test_a_naive_instant_is_refused():
    # A naive value would be read as the server's local time, which is wrong on any
    # server that is not set to UTC.
    with pytest.raises(ValueError, match="timezone-aware"):
        local_now(user_in("Asia/Kolkata"), INSTANT.replace(tzinfo=None))
