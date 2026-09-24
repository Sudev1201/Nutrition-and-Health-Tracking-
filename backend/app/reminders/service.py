"""Reminder settings, and the devices reminders are pushed to.

A reminder setting is not a table of its own. `reminder_on` sits on the profile's
`meal_slot_times` rows and is edited there in place, so the times a reminder
fires at are the diary's and the planner's, never a copy that drifts from them.

A device is a `push_subscriptions` row. It belongs to the user, not the profile,
so a profile save -- which replaces every meal-time row -- leaves it subscribed.
"""

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.profile import MealSlotTime
from app.models.push import PushSubscription
from app.models.user import User
from app.profiles import service as profiles

# The widths of the columns these land in. A User-Agent header has no length
# limit, and cutting one to fit beats a 500 from Postgres.
USER_AGENT_LENGTH = 300
TIMEZONE_LENGTH = 64


class NoProfile(LookupError):
    """No profile, so no meal times to remind about."""


class UnknownSlot(ValueError):
    """A slot that does not exist, or one switched off in the profile."""


@dataclass(frozen=True)
class SlotReminder:
    slot: str
    time: datetime.time
    # Used on Saturday and Sunday when set, as the planner does.
    weekend_time: datetime.time | None
    reminder_on: bool


def reminder_slots(db: Session, user: User) -> list[SlotReminder]:
    """The enabled slots, in meal order, with their times and reminder switch.

    A slot with no row is one the profile was saved without -- a profile from
    before meal times existed -- so it is on, at its default time, as the diary
    and the planner already treat it. A slot switched off is left out: nothing
    is eaten there on a normal day, so there is nothing to remind about.
    """
    if profiles.get_profile(db, user) is None:
        raise NoProfile
    # `get_meal_times` orders by primary key, which is a random UUID.
    rows = {row.slot: row for row in profiles.get_meal_times(db, user)}

    reminders = []
    for slot in SLOTS:
        row = rows.get(slot)
        if row is None:
            reminders.append(
                SlotReminder(slot, _default_time(slot), None, _reminder_by_default(slot))
            )
        elif row.is_enabled:
            reminders.append(SlotReminder(slot, row.usual_time, row.weekend_time, row.reminder_on))
    return reminders


def set_reminder(db: Session, user: User, slot: str, on: bool) -> None:
    """Turn one slot's reminder on or off, on the profile's own row.

    A profile saved before meal times existed has no row to edit, so one is
    created at the slot's default time -- the time it was already shown at.
    There is one row per slot (`uq_meal_time_user_slot`), so a second call
    updates the row the first created.
    """
    if profiles.get_profile(db, user) is None:
        raise NoProfile
    if slot not in SLOTS:
        raise UnknownSlot(f"Unknown slot {slot!r}")

    row = db.scalars(
        select(MealSlotTime).where(MealSlotTime.user_id == user.id, MealSlotTime.slot == slot)
    ).one_or_none()
    if row is None:
        db.add(
            MealSlotTime(
                user_id=user.id,
                slot=slot,
                usual_time=_default_time(slot),
                weekend_time=None,
                reminder_on=on,
                is_enabled=True,
            )
        )
    elif not row.is_enabled:
        # Switching a snack back on belongs to the profile, which owns the shape
        # of a normal day. A reminder switch must not quietly do it instead.
        raise UnknownSlot(f"{slot} is switched off in your profile, so it has no reminder")
    else:
        row.reminder_on = on
    db.flush()


def save_subscription(
    db: Session,
    user: User,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
    timezone: str | None,
) -> PushSubscription:
    """Store a browser's push subscription, keyed by its endpoint, for this user.

    The endpoint names one browser install. Posted again from another account,
    the row moves to that account, so a shared phone reminds only whoever
    subscribed it last. One statement rather than a read and a write: two
    posts of the same endpoint cannot both insert.

    Also records the browser's timezone on the user, when this server can
    resolve it. Nothing else writes it, and reminder times are wall-clock.
    """
    values = {
        "user_id": user.id,
        "endpoint": endpoint,
        "p256dh": p256dh,
        "auth": auth,
        "user_agent": user_agent[:USER_AGENT_LENGTH] if user_agent else None,
    }
    statement = insert(PushSubscription).values(**values)
    statement = statement.on_conflict_do_update(
        constraint="uq_push_endpoint",
        set_={name: statement.excluded[name] for name in values if name != "endpoint"},
    )
    subscription = db.scalars(
        statement.returning(PushSubscription),
        # The row may already be in this session under its previous owner. Load
        # what the statement returned over it, not what the session remembers.
        execution_options={"populate_existing": True},
    ).one()

    if timezone and _is_zone(timezone):
        user.timezone = timezone
    db.flush()
    return subscription


def delete_subscription(db: Session, user: User, endpoint: str) -> bool:
    """Forget one of this user's devices. False when the endpoint is not theirs."""
    row = db.scalars(
        select(PushSubscription).where(
            PushSubscription.user_id == user.id, PushSubscription.endpoint == endpoint
        )
    ).one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def device_count(db: Session, user: User) -> int:
    return db.scalar(
        select(func.count())
        .select_from(PushSubscription)
        .where(PushSubscription.user_id == user.id)
    )


def _default_time(slot: str) -> datetime.time:
    return datetime.time.fromisoformat(DEFAULT_SLOT_TIMES[slot])


def _reminder_by_default(slot: str) -> bool:
    # The mid-morning snack is the one most often not eaten, so a reminder there
    # is opt-in: the default a profile save gives a new slot.
    return slot != "snack1"


def _is_zone(name: str) -> bool:
    """A zone this server resolves, so `local_today` never falls back to UTC on it."""
    if len(name) > TIMEZONE_LENGTH:
        return False
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True
