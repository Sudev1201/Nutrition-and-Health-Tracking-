"""Where a reminder goes. A channel delivers one reminder to one user.

The runner decides what is due and claims it. A channel only delivers, and
answers "sent", "failed" or "no-device", which the runner records on the claim.
Web push is the first channel. Another one, such as an email or a WhatsApp
message, would be another class with the same `send`, and the runner would not
change.
"""

import json
import logging
from typing import Protocol

import pywebpush
import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.push import PushSubscription
from app.models.user import User
from app.reminders.schedule import Reminder

logger = logging.getLogger(__name__)

# What a push service answers for a subscription that no longer exists. The user
# revoked the permission or cleared the site's data, or the browser moved to a new
# endpoint. RFC 8030 says to stop sending to it, and a row left behind would fail
# again at every meal.
GONE_STATUSES = frozenset({404, 410})

# How long to wait on one push service. The tick sends to every user in turn, so
# one hung push service must not hold up everyone after it.
PUSH_TIMEOUT_SECONDS = 10


class Channel(Protocol):
    def send(self, db: Session, user: User, reminder: Reminder) -> str:
        """Deliver `reminder` to `user`, and answer "sent", "failed" or "no-device"."""


class WebPushChannel:
    """Browser push, signed with the server's VAPID key (RFC 8292)."""

    # How long a push service holds the reminder for a phone that is off or offline.
    # A slot is claimed within a minute of its time, so this lapses before the
    # slot's hour is over. A reminder that arrives later than that is about a meal
    # already eaten, and it is better dropped.
    TTL_SECONDS = 45 * 60

    def __init__(self, private_key: str, subject: str) -> None:
        self._private_key = private_key
        self._subject = subject

    def send(self, db: Session, user: User, reminder: Reminder) -> str:
        """Push to every device the user subscribed. "sent" when any of them took it."""
        subscriptions = list(
            db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id))
        )
        if not subscriptions:
            return "no-device"

        # The service worker shows exactly this. It never stays silent, because
        # Chrome penalises a push that shows nothing and Safari can revoke it.
        payload = json.dumps(
            {
                "title": reminder.title,
                "body": reminder.body,
                "url": reminder.url,
                "tag": reminder.tag,
            }
        )
        outcomes = [self._push(subscription, payload) for subscription in subscriptions]
        for subscription, outcome in zip(subscriptions, outcomes, strict=True):
            if outcome == "gone":
                db.delete(subscription)
        db.flush()

        if "sent" in outcomes:
            return "sent"
        if all(outcome == "gone" for outcome in outcomes):
            return "no-device"
        return "failed"

    def _push(self, subscription: PushSubscription, payload: str) -> str:
        """Push to one device: "sent", "gone" (the push service forgot it) or "failed"."""
        try:
            pywebpush.webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=self._private_key,
                # A new dict for every push. webpush writes the endpoint's origin into
                # the dict as the token's audience. A dict reused across devices would
                # sign the second push for the first device's push service, and the
                # second push service would refuse it.
                vapid_claims={"sub": self._subject},
                ttl=self.TTL_SECONDS,
                timeout=PUSH_TIMEOUT_SECONDS,
            )
        except pywebpush.WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in GONE_STATUSES:
                return "gone"
            logger.warning("web push refused with status %s", status)
            return "failed"
        except requests.RequestException:
            logger.warning("web push could not reach the push service", exc_info=True)
            return "failed"
        except (ValueError, IndexError):
            # Keys no browser would send, which the subscribe route lets through
            # because it checks only their length: one that is not base64url, or
            # not a point on P-256. A VAPID private key that does not parse lands
            # here too. This device fails and the user's other devices are still
            # pushed. It is not "gone": a bad server key must not delete every
            # subscription.
            logger.warning("web push could not encrypt or sign for this device", exc_info=True)
            return "failed"
        return "sent"
