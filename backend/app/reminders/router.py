"""Reminder settings, and the devices reminders are pushed to.

Two routers, because the settings are a screen's worth of state while the push
routes are the browser's side of a web-push subscription.
"""

import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import settings
from app.db import get_db
from app.models.user import User
from app.reminders import service

settings_router = APIRouter(prefix="/settings", tags=["settings"])
push_router = APIRouter(prefix="/push", tags=["push"])

NOT_SET_UP = "Reminders are not set up on this server"


class ReminderSlotOut(BaseModel):
    slot: str
    time: str
    weekend_time: str | None
    reminder_on: bool


class RemindersOut(BaseModel):
    slots: list[ReminderSlotOut]
    # This user's subscribed browsers. Whether the one asking is among them, and
    # whether it may show notifications at all, are facts only that browser has.
    devices: int


class ReminderIn(BaseModel):
    slot: str
    reminder_on: bool


class PublicKeyOut(BaseModel):
    key: str


class PushKeysIn(BaseModel):
    # The widths of the columns they are stored in.
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class SubscriptionIn(BaseModel):
    """What the browser's `PushSubscription.toJSON()` gives, plus its timezone.

    `expirationTime` is ignored; browsers leave it null.
    """

    # The server POSTs to this URL. A push service is always https, and refusing
    # anything else closes the easiest way to aim the server's requests at a
    # plain-http service on its own network.
    endpoint: str = Field(max_length=2048, pattern=r"^https://")
    keys: PushKeysIn
    # The browser's IANA zone. One this server cannot resolve is ignored rather
    # than refused: the subscription is still good.
    timezone: str | None = None


class DevicesOut(BaseModel):
    devices: int


class UnsubscribeIn(BaseModel):
    endpoint: str


def _hhmm(value: datetime.time) -> str:
    return value.strftime("%H:%M")


def _out(db: Session, user: User) -> RemindersOut:
    return RemindersOut(
        slots=[
            ReminderSlotOut(
                slot=item.slot,
                time=_hhmm(item.time),
                weekend_time=_hhmm(item.weekend_time) if item.weekend_time else None,
                reminder_on=item.reminder_on,
            )
            for item in service.reminder_slots(db, user)
        ],
        devices=service.device_count(db, user),
    )


@settings_router.get("/reminders", response_model=RemindersOut)
def read_reminders(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> RemindersOut:
    try:
        return _out(db, user)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


@settings_router.patch("/reminders", response_model=RemindersOut)
def update_reminder(
    payload: ReminderIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemindersOut:
    try:
        service.set_reminder(db, user, payload.slot, payload.reminder_on)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    except service.UnknownSlot as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    db.commit()
    return _out(db, user)


@push_router.get(
    "/public-key", response_model=PublicKeyOut, dependencies=[Depends(get_current_user)]
)
def read_public_key() -> PublicKeyOut:
    # Both halves, not only the one handed out: a browser subscribed to a key the
    # server cannot sign with would wait for reminders that never come.
    if not (settings.vapid_public_key and settings.vapid_private_key):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP)
    return PublicKeyOut(key=settings.vapid_public_key)


@push_router.post("/subscriptions", response_model=DevicesOut, status_code=status.HTTP_201_CREATED)
def subscribe(
    payload: SubscriptionIn,
    user_agent: str | None = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DevicesOut:
    service.save_subscription(
        db,
        user,
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=user_agent,
        timezone=payload.timezone,
    )
    db.commit()
    return DevicesOut(devices=service.device_count(db, user))


@push_router.delete("/subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    payload: UnsubscribeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    # Another user's endpoint is as unknown as a made-up one: which devices
    # someone else has is not this caller's to find out.
    if not service.delete_subscription(db, user, payload.endpoint):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such device")
    db.commit()
