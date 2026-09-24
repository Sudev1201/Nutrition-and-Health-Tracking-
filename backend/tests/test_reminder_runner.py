"""The runner: the due slots of subscribed users, each claimed once, then sent.

The channel here is a fake that records what it was handed. These tests cover
the deciding and the claiming; test_webpush_channel.py covers the delivery.

Every tick is at a fixed time on the real today in Kolkata. A profile save
records a weigh-in dated today, so the day must be the real one. A fixed time of
day keeps the tests clear of midnight and of the edges of a slot's hour. PROFILE
puts breakfast at 08:00, and saves the mid-morning snack's reminder off.
"""

import asyncio
import datetime
import zoneinfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import main
from app.config import settings
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User
from app.reminders import runner
from app.reminders.channels import WebPushChannel
from app.reminders.schedule import Reminder, reminder_for
from scripts import send_reminders
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def at(hour: int, minute: int, zone: datetime.tzinfo = KOLKATA) -> datetime.datetime:
    """A time on today's wall clock in `zone`, as the UTC instant the runner takes."""
    local = datetime.datetime.combine(TODAY, datetime.time(hour, minute), tzinfo=zone)
    return local.astimezone(datetime.UTC)


class FakeChannel:
    """Records every reminder it is handed, and answers `outcome`."""

    def __init__(self, outcome: str = "sent") -> None:
        self.outcome = outcome
        self.sent: list[tuple[str, Reminder]] = []

    def send(self, db, user: User, reminder: Reminder) -> str:
        self.sent.append((user.email, reminder))
        return self.outcome


class BrokenChannel:
    def send(self, db, user: User, reminder: Reminder) -> str:
        raise RuntimeError("the push library fell over")


def subscribe(db, user: User) -> None:
    db.add(
        PushSubscription(
            user_id=user.id,
            endpoint=f"https://push.example.com/{user.google_sub}",
            p256dh="p" * 87,
            auth="a" * 22,
        )
    )
    db.flush()


def deliveries(db, user: User) -> list[tuple[str, datetime.date, str]]:
    rows = db.scalars(
        select(ReminderDelivery)
        .where(ReminderDelivery.user_id == user.id)
        .order_by(ReminderDelivery.local_date, ReminderDelivery.slot)
    )
    return [(row.slot, row.local_date, row.status) for row in rows]


def log_food(api, dish, slot: str) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(TODAY),
            "slot": slot,
            "food_id": str(dish.id),
            "food_kind": "dish",
            "grams": 150,
            "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    """The signed-in user, with a profile and one subscribed device."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    found = db.scalar(select(User).where(User.email == "track@example.com"))
    subscribe(db, found)
    return found


def test_a_due_slot_with_nothing_logged_is_reminded(db, user):
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 1

    assert channel.sent == [("track@example.com", reminder_for("breakfast", TODAY))]
    assert deliveries(db, user) == [("breakfast", TODAY, "sent")]


def test_a_reminder_goes_once_however_often_the_runner_ticks(db, user):
    channel = FakeChannel()
    runner.tick(db, at(8, 10), channel)

    assert runner.tick(db, at(8, 11), channel) == 0
    assert runner.tick(db, at(8, 55), channel) == 0
    assert len(channel.sent) == 1


def test_a_reminder_another_runner_claimed_is_not_sent_again(db, user):
    """An overlapping cron run, a second instance, or a tick from before a restart."""
    db.add(ReminderDelivery(user_id=user.id, local_date=TODAY, slot="breakfast", status="sent"))
    db.flush()
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_yesterdays_reminder_does_not_count_for_today(db, user):
    yesterday = TODAY - datetime.timedelta(days=1)
    db.add(ReminderDelivery(user_id=user.id, local_date=yesterday, slot="breakfast", status="sent"))
    db.flush()

    assert runner.tick(db, at(8, 10), FakeChannel()) == 1


def test_a_logged_slot_is_not_reminded(db, user, signed_in, reference_data):
    log_food(signed_in, reference_data, "breakfast")
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    # Nothing was claimed either: the reminder was never due.
    assert deliveries(db, user) == []


def test_food_in_another_slot_does_not_account_for_this_one(db, user, signed_in, reference_data):
    log_food(signed_in, reference_data, "lunch")
    assert runner.tick(db, at(8, 10), FakeChannel()) == 1


def test_a_skipped_slot_is_not_reminded(db, user, signed_in):
    skipped = signed_in.post("/diary/skips", json={"date": str(TODAY), "slot": "breakfast"})
    assert skipped.status_code == 201
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_a_reminder_turned_off_in_settings_is_not_sent(db, user, signed_in):
    turned_off = signed_in.patch(
        "/settings/reminders", json={"slot": "breakfast", "reminder_on": False}
    )
    assert turned_off.status_code == 200
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []


def test_a_slot_saved_with_its_reminder_off_is_not_sent(db, user):
    # 11:10 is ten minutes into the mid-morning snack, which PROFILE saves with its
    # reminder off. No other slot is due then.
    channel = FakeChannel()
    assert runner.tick(db, at(11, 10), channel) == 0
    assert channel.sent == []


def test_a_tick_more_than_an_hour_late_sends_nothing(db, user):
    # The runner was down from before 08:00 until 09:05: breakfast's hour is over.
    channel = FakeChannel()

    assert runner.tick(db, at(9, 5), channel) == 0
    assert channel.sent == []
    assert deliveries(db, user) == []


def test_the_slot_time_is_the_users_own_wall_clock(db, user):
    user.timezone = "UTC"
    db.flush()
    channel = FakeChannel()

    # 08:10 in Kolkata is 02:40 in UTC, hours before this user's breakfast.
    assert runner.tick(db, at(8, 10), channel) == 0
    assert runner.tick(db, at(8, 10, datetime.UTC), channel) == 1
    assert [reminder.local_date for _, reminder in channel.sent] == [TODAY]


def test_a_user_with_no_device_is_not_considered(db, signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    user = db.scalar(select(User).where(User.email == "track@example.com"))
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    assert deliveries(db, user) == []


def test_a_device_with_no_profile_behind_it_is_passed_over(db):
    stranger = User(google_sub="sub-stranger", email="stranger@example.com", name="Stranger")
    db.add(stranger)
    db.flush()
    subscribe(db, stranger)
    channel = FakeChannel()

    assert runner.tick(db, at(8, 10), channel) == 0
    assert channel.sent == []
    assert deliveries(db, stranger) == []


@pytest.mark.parametrize("outcome", ["failed", "no-device"])
def test_the_channels_answer_is_recorded_and_not_retried(db, user, outcome):
    channel = FakeChannel(outcome)

    assert runner.tick(db, at(8, 10), channel) == 0
    assert runner.tick(db, at(8, 11), channel) == 0

    assert len(channel.sent) == 1
    assert deliveries(db, user) == [("breakfast", TODAY, outcome)]


def test_a_channel_that_raises_is_recorded_as_a_failure(db, user):
    assert runner.tick(db, at(8, 10), BrokenChannel()) == 0
    assert deliveries(db, user) == [("breakfast", TODAY, "failed")]


class Stop(BaseException):
    """Ends run_forever from inside a tick. `except Exception` must let it through."""


def test_the_loop_ticks_again_after_a_failed_tick(monkeypatch):
    channels = []

    def fake_run_once(channel) -> int:
        channels.append(channel)
        if len(channels) == 1:
            raise RuntimeError("the database is restarting")
        if len(channels) == 3:
            raise Stop
        return 0

    monkeypatch.setattr(runner, "run_once", fake_run_once)

    with pytest.raises(Stop):
        asyncio.run(runner.run_forever(interval_seconds=0))

    assert len(channels) == 3
    assert all(isinstance(channel, WebPushChannel) for channel in channels)


def recording_loop(events: list[str]):
    """A stand-in for run_forever that records when it starts and when it stops."""

    async def fake_run_forever(interval_seconds: int = 60) -> None:
        events.append("started")
        try:
            await asyncio.Event().wait()
        finally:
            events.append("stopped")

    return fake_run_forever


def test_the_api_runs_the_loop_when_enabled_and_stops_it_on_shutdown(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "vapid_private_key", "a-private-key")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200
        assert events == ["started"]

    assert events == ["started", "stopped"]


def test_the_suite_keeps_the_loop_off(monkeypatch):
    """conftest turns SCHEDULER_ENABLED off, so a key alone starts nothing."""
    events: list[str] = []
    monkeypatch.setattr(settings, "vapid_private_key", "a-private-key")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

    assert events == []


def test_the_loop_needs_a_key_to_sign_with(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    monkeypatch.setattr(settings, "vapid_private_key", "")
    monkeypatch.setattr(main, "run_forever", recording_loop(events))

    with TestClient(main.app) as client:
        assert client.get("/health").status_code == 200

    assert events == []


def test_the_cron_script_needs_a_key(monkeypatch):
    monkeypatch.setattr(settings, "vapid_private_key", "")
    assert send_reminders.main() == 1
