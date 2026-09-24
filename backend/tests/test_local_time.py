"""A user's today is their date, not the server's -- and a garbage zone does not break it."""

import datetime
import zoneinfo

from app.local_time import local_today
from app.models.user import User


def test_today_is_the_date_where_the_user_is():
    user = User(google_sub="s", email="e@example.com", name="n", timezone="Asia/Kolkata")
    assert local_today(user) == datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()


def test_an_unknown_timezone_falls_back_to_utc():
    user = User(google_sub="s", email="e@example.com", name="n", timezone="Not/AZone")
    assert local_today(user) == datetime.datetime.now(datetime.UTC).date()
