"""Which meal reminders are due. Pure: no database and no clock.

A slot is due for an hour from its time, by the user's wall clock and on their
date. It is due only if its reminder is on and the diary does not already
account for it. A logged slot needs no nudge. A skipped slot is an explicit "not
eating this", so nagging after it would be wrong.

The hour is also the limit on lateness. A runner that was down at 08:00 and
comes back at 09:05 sends nothing for breakfast. By then the reminder would be
about a meal already eaten, or already missed.
"""

import datetime
from collections.abc import Sequence
from dataclasses import dataclass

from app.meal_slots import SLOTS
from app.planner.rules import sunday_index
from app.reminders.service import SlotReminder

LATE_LIMIT = datetime.timedelta(minutes=60)

SLOT_TITLES = {
    "breakfast": "Breakfast",
    "snack1": "Mid-morning snack",
    "lunch": "Lunch",
    "snack2": "Evening snack",
    "dinner": "Dinner",
}


@dataclass(frozen=True)
class Reminder:
    """One notification, as the channel sends it and the service worker shows it."""

    slot: str
    local_date: datetime.date
    title: str
    body: str
    # Where a tap on the notification opens.
    url: str
    # One notification per slot and day. A second push with the same tag replaces
    # the first on the device rather than stacking beside it.
    tag: str


def slot_time_on(reminder: SlotReminder, day: datetime.date) -> datetime.time:
    """The slot's time on `day`: its weekend time on Saturday and Sunday, when it has one.

    This is the planner's rule, so a reminder and the plan agree on when a meal is.
    """
    if sunday_index(day) in (0, 6) and reminder.weekend_time is not None:
        return reminder.weekend_time
    return reminder.time


def due_slots(
    local_now: datetime.datetime,
    reminders: Sequence[SlotReminder],
    accounted: frozenset[str],
) -> list[str]:
    """The slots to remind about at `local_now`, in meal order.

    `accounted` holds the slots the diary already has an answer for, logged or
    skipped. Only the slot on `local_now`'s own date counts, so a 23:30 dinner is
    not reminded at 00:10: that is another day, with its own diary.
    """
    day = local_now.date()
    due = set()
    for reminder in reminders:
        if not reminder.reminder_on or reminder.slot in accounted:
            continue
        # The same tzinfo as `local_now`, so the comparison is on the wall clock.
        start = datetime.datetime.combine(day, slot_time_on(reminder, day), tzinfo=local_now.tzinfo)
        if start <= local_now < start + LATE_LIMIT:
            due.add(reminder.slot)
    return [slot for slot in SLOTS if slot in due]


def reminder_for(slot: str, day: datetime.date) -> Reminder:
    title = SLOT_TITLES[slot]
    return Reminder(
        slot=slot,
        local_date=day,
        title=title,
        body=f"Nothing logged for {title.lower()} yet. Tap to log it.",
        url=f"/log?slot={slot}",
        tag=f"{slot}-{day.isoformat()}",
    )
