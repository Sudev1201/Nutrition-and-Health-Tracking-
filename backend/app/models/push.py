import datetime
import uuid

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class PushSubscription(TimestampedBase):
    """One browser's web-push endpoint, and the keys a payload is encrypted to.

    Unique on the endpoint across every user, not per user: the push service mints
    one endpoint per browser install, so the endpoint names a device. When a second
    account subscribes the same browser, the row moves to that account -- a shared
    phone reminds whoever subscribed it last, and never shows one person's meal
    nudges to another.

    Not one of the profile's child tables, and it must never become one: a profile
    save deletes those, and editing a meal time must not unsubscribe every device.
    """

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_endpoint"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The push service's URL for this browser. Text, because nothing bounds its length.
    endpoint: Mapped[str] = mapped_column(Text)
    # The browser's P-256 public key and auth secret (RFC 8291), base64url-encoded:
    # 87 and 22 characters in practice.
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    # Which device this is, for a person reading their own list. A User-Agent header
    # has no length limit, so whatever stores it cuts it to 300 characters first.
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ReminderDelivery(TimestampedBase):
    """A claim on one reminder: one user, one local date, one slot.

    Inserted before anything is sent, with INSERT ... ON CONFLICT DO NOTHING
    RETURNING, and only the call that gets a row back sends. The unique key is the
    whole of "exactly once": a restart, an overlapping cron run or a second instance
    each lose the insert, instead of trusting a memory of what already went out.

    The price is that a failed send is not retried. For a nudge, at most once is the
    right side to err on: a reminder sent twice is noise, and a retry that lands an
    hour late is about a meal already eaten.
    """

    __tablename__ = "reminder_deliveries"
    __table_args__ = (
        UniqueConstraint("user_id", "local_date", "slot", name="uq_delivery_user_day_slot"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # The user's local date, matching `MealLog.logged_on`: the slot's day is theirs.
    local_date: Mapped[datetime.date] = mapped_column(Date)
    slot: Mapped[str] = mapped_column(String(12))
    # sent | failed | no-device: what the channel answered. The claim goes in before
    # the send, as failed, and is corrected once the channel answers -- so a crash
    # between the two reads as not delivered rather than as delivered.
    status: Mapped[str] = mapped_column(String(12))
