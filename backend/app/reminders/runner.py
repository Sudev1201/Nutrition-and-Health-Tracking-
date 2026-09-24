"""The reminder runner. It works out what is due, claims it once, and sends it.

`tick` is one pass at one instant. It takes every user who has a subscribed
device and a profile, reads their wall clock and their meal times, and asks the
schedule which slots are due. It drops the slots the diary already accounts for,
logged or skipped.

Each remaining reminder is claimed with INSERT ... ON CONFLICT DO NOTHING
RETURNING before anything is sent, and only the tick that gets the row back
sends it. The unique key on (user, local date, slot) is the whole of "exactly
once". An earlier tick, an overlapping cron run and a second instance all lose
that insert, so nothing has to remember what already went out.

A claim goes in as failed and is then set to the channel's answer. A reminder
is never retried: for a nudge, at most once is the right side to err on.

`run_forever` is the loop the API's lifespan starts. `scripts.send_reminders`
runs one tick for an external cron. Each commits after its tick, and both may
run at the same time.
"""

import asyncio
import datetime
import logging
import uuid

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.diary import service as diary
from app.local_time import local_now
from app.models.profile import Profile
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User
from app.reminders import service as reminders
from app.reminders.channels import Channel, WebPushChannel
from app.reminders.schedule import Reminder, due_slots, reminder_for

logger = logging.getLogger(__name__)


def tick(db: Session, now_utc: datetime.datetime, channel: Channel) -> int:
    """Send every reminder due at `now_utc` that has not gone yet. Returns how many were sent."""
    sent = 0
    for user in _reminded_users(db):
        local = local_now(user, now_utc)
        day = local.date()
        times = reminders.reminder_slots(db, user)
        # Most ticks find nothing due for anyone, so the clock rules a user out
        # before their diary is read.
        if not due_slots(local, times, frozenset()):
            continue
        states = diary.slot_states(db, user, day)
        accounted = frozenset(slot for slot, state in states.items() if state != "empty")

        for slot in due_slots(local, times, accounted):
            claim = _claim(db, user, day, slot)
            if claim is None:
                # Claimed already, by an earlier tick, a cron run or another instance.
                continue
            # The claim is made durable BEFORE anything is sent: a crash after the send
            # can then never send it again. At most once is the right failure mode for
            # a nudge -- a missed reminder costs less than a duplicate. This is the one
            # place outside a router that commits; the runner is the job's entry point.
            db.commit()
            outcome = _deliver(db, user, reminder_for(slot, day), channel)
            db.execute(
                update(ReminderDelivery).where(ReminderDelivery.id == claim).values(status=outcome)
            )
            db.commit()
            if outcome == "sent":
                sent += 1
    return sent


def run_once(channel: Channel) -> int:
    """One tick at the current instant, in its own session, committed."""
    with SessionLocal() as db:
        sent = tick(db, datetime.datetime.now(datetime.UTC), channel)
        db.commit()
    return sent


async def run_forever(interval_seconds: int = 60) -> None:
    """Tick every `interval_seconds` until cancelled. The API's lifespan runs this."""
    channel = WebPushChannel(settings.vapid_private_key, settings.vapid_subject)
    while True:
        try:
            # The backend is sync: the session, psycopg and pywebpush's requests.
            # So the tick runs in a worker thread, off the loop that serves the API.
            await asyncio.to_thread(run_once, channel)
        except Exception:
            # A database restart or a network blip costs one tick, not the loop.
            # Every claim is committed before its send, so a failed tick sends
            # nothing twice; a reminder it had not claimed yet is decided again
            # by the next tick within the slot's hour.
            logger.exception("reminder tick failed")
        await asyncio.sleep(interval_seconds)


def _reminded_users(db: Session) -> list[User]:
    """Users with a subscribed device and a profile, in id order.

    A device with no profile behind it has no meals to remind about. The fixed
    order makes two runners claim in the same order, so neither can hold a claim
    the other needs while it waits on one of the other's.
    """
    has_device = select(PushSubscription.id).where(PushSubscription.user_id == User.id).exists()
    has_profile = select(Profile.id).where(Profile.user_id == User.id).exists()
    return list(db.scalars(select(User).where(has_device, has_profile).order_by(User.id)))


def _claim(db: Session, user: User, day: datetime.date, slot: str) -> uuid.UUID | None:
    """Claim one reminder. Returns the new row's id, or None when it was claimed already."""
    return db.execute(
        insert(ReminderDelivery)
        .values(user_id=user.id, local_date=day, slot=slot, status="failed")
        .on_conflict_do_nothing(constraint="uq_delivery_user_day_slot")
        .returning(ReminderDelivery.id)
    ).scalar_one_or_none()


def _deliver(db: Session, user: User, reminder: Reminder, channel: Channel) -> str:
    """The channel's answer, or "failed" when the channel raised."""
    try:
        return channel.send(db, user, reminder)
    except Exception:
        # One user's failed send must not end the tick for everyone after them.
        # The claim is already committed as failed, and stays failed: a reminder
        # is never retried.
        logger.exception("sending the %s reminder failed", reminder.tag)
        return "failed"
