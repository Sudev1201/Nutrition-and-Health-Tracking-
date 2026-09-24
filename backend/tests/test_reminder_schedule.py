"""When a meal reminder is due. Pure, and on fixed dates.

A slot is due for an hour from its time, by the user's wall clock and on their
date. Its weekend time applies on Saturday and Sunday. It is never due once the
meal is logged or skipped, or while its reminder is off. 17 August 2026 is a
Monday, and the 22nd and 23rd are the weekend after it.
"""

import datetime
from zoneinfo import ZoneInfo

import pytest

from app.meal_slots import SLOTS
from app.reminders.schedule import (
    LATE_LIMIT,
    SLOT_TITLES,
    Reminder,
    due_slots,
    reminder_for,
    slot_time_on,
)
from app.reminders.service import SlotReminder

KOLKATA = ZoneInfo("Asia/Kolkata")
MONDAY = datetime.date(2026, 8, 17)
SATURDAY = datetime.date(2026, 8, 22)
SUNDAY = datetime.date(2026, 8, 23)

NOTHING: frozenset[str] = frozenset()


def meal(
    slot: str,
    hour: int,
    minute: int = 0,
    weekend: datetime.time | None = None,
    on: bool = True,
) -> SlotReminder:
    return SlotReminder(
        slot=slot, time=datetime.time(hour, minute), weekend_time=weekend, reminder_on=on
    )


def clock(day: datetime.date, hour: int, minute: int, second: int = 0) -> datetime.datetime:
    """A moment on the user's wall clock in Kolkata."""
    return datetime.datetime.combine(day, datetime.time(hour, minute, second), tzinfo=KOLKATA)


BREAKFAST = meal("breakfast", 8, weekend=datetime.time(9, 30))


def test_the_late_limit_is_an_hour():
    assert LATE_LIMIT == datetime.timedelta(minutes=60)


@pytest.mark.parametrize(
    ("hour", "minute", "second", "due"),
    [
        (7, 59, 59, False),  # not yet
        (8, 0, 0, True),  # from the slot's time
        (8, 59, 59, True),  # through the hour after it
        (9, 0, 0, False),  # an hour late sends nothing rather than a stale nudge
    ],
)
def test_a_slot_is_due_for_the_hour_from_its_time(hour, minute, second, due):
    now = clock(MONDAY, hour, minute, second)
    assert due_slots(now, [BREAKFAST], NOTHING) == (["breakfast"] if due else [])


def test_a_slot_whose_reminder_is_off_is_never_due():
    snack = meal("snack1", 11, on=False)
    assert due_slots(clock(MONDAY, 11, 10), [snack], NOTHING) == []


def test_a_slot_the_diary_accounts_for_is_not_due():
    # The runner passes logged and skipped slots alike.
    assert due_slots(clock(MONDAY, 8, 10), [BREAKFAST], frozenset({"breakfast"})) == []


def test_another_slot_being_accounted_for_does_not_hide_this_one():
    assert due_slots(clock(MONDAY, 8, 10), [BREAKFAST], frozenset({"lunch"})) == ["breakfast"]


def test_due_slots_come_in_meal_order():
    early_lunch = meal("lunch", 11, 30)
    snack = meal("snack1", 11)
    now = clock(MONDAY, 11, 40)
    assert due_slots(now, [early_lunch, snack], NOTHING) == ["snack1", "lunch"]


@pytest.mark.parametrize("day", [SATURDAY, SUNDAY])
def test_the_weekend_time_applies_on_saturday_and_sunday(day):
    assert slot_time_on(BREAKFAST, day) == datetime.time(9, 30)
    assert due_slots(clock(day, 8, 10), [BREAKFAST], NOTHING) == []
    assert due_slots(clock(day, 9, 40), [BREAKFAST], NOTHING) == ["breakfast"]


def test_a_weekday_keeps_the_usual_time():
    assert slot_time_on(BREAKFAST, MONDAY) == datetime.time(8, 0)
    assert due_slots(clock(MONDAY, 9, 40), [BREAKFAST], NOTHING) == []


def test_a_weekend_without_its_own_time_keeps_the_usual_one():
    assert slot_time_on(meal("lunch", 13, 30), SUNDAY) == datetime.time(13, 30)


def test_a_late_dinner_is_not_reminded_on_the_next_day():
    dinner = meal("dinner", 23, 30)
    assert due_slots(clock(MONDAY, 23, 50), [dinner], NOTHING) == ["dinner"]
    # 00:10 on Tuesday is 40 minutes after Monday's dinner, but on another date.
    # Tuesday's own dinner is nearly a day away, and Monday's diary is not Tuesday's.
    tuesday = MONDAY + datetime.timedelta(days=1)
    assert due_slots(clock(tuesday, 0, 10), [dinner], NOTHING) == []


def test_the_reminder_names_the_meal_and_links_to_logging_it():
    assert reminder_for("snack1", MONDAY) == Reminder(
        slot="snack1",
        local_date=MONDAY,
        title="Mid-morning snack",
        body="Nothing logged for mid-morning snack yet. Tap to log it.",
        url="/log?slot=snack1",
        tag="snack1-2026-08-17",
    )


def test_every_slot_has_a_title():
    assert set(SLOT_TITLES) == set(SLOTS)
