"""Web push goes to every device the user subscribed, signed for each push service.
A device the push service has forgotten is forgotten here too.

`pywebpush.webpush` is replaced by a fake. It behaves like the real one in the
two ways that matter here. It writes the endpoint's origin into the claims dict
it is handed, and it raises WebPushException carrying the push service's
response.
"""

import datetime
import json
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest
import pywebpush
import requests
from sqlalchemy import select

from app.models.push import PushSubscription
from app.models.user import User
from app.reminders.channels import WebPushChannel
from app.reminders.schedule import reminder_for

DAY = datetime.date(2026, 8, 17)
PHONE = "https://fcm.googleapis.com/fcm/send/phone-token"
LAPTOP = "https://updates.push.services.mozilla.com/wpush/v2/laptop-token"
PRIVATE_KEY = "vapid-private-key"
SUBJECT = "mailto:reminders@example.com"


class FakePushService:
    """Stands in for pywebpush.webpush. Records each push, and refuses the endpoints
    in `refusals`."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.refusals: dict[str, Exception] = {}

    def __call__(self, **kwargs) -> SimpleNamespace:
        endpoint = kwargs["subscription_info"]["endpoint"]
        claims = kwargs["vapid_claims"]
        # What the real webpush does to the claims it is handed.
        if not claims.get("aud"):
            origin = urlparse(endpoint)
            claims["aud"] = f"{origin.scheme}://{origin.netloc}"
        self.calls.append({**kwargs, "vapid_claims": dict(claims)})
        if endpoint in self.refusals:
            raise self.refusals[endpoint]
        return SimpleNamespace(status_code=201)

    def endpoints(self) -> set[str]:
        return {call["subscription_info"]["endpoint"] for call in self.calls}


@pytest.fixture
def push_service(monkeypatch) -> FakePushService:
    fake = FakePushService()
    monkeypatch.setattr(pywebpush, "webpush", fake)
    return fake


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def user(db) -> User:
    return make_user(db, "push")


def subscribe(db, user: User, endpoint: str) -> None:
    token = endpoint.rsplit("/", 1)[-1]
    db.add(
        PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh=f"p256dh-{token}", auth=f"auth-{token}"
        )
    )
    db.flush()


def endpoints(db, user: User) -> set[str]:
    return set(
        db.scalars(select(PushSubscription.endpoint).where(PushSubscription.user_id == user.id))
    )


def send(db, user: User) -> str:
    return WebPushChannel(PRIVATE_KEY, SUBJECT).send(db, user, reminder_for("lunch", DAY))


def refusal(status: int) -> pywebpush.WebPushException:
    return pywebpush.WebPushException(
        f"Push failed: {status}", response=SimpleNamespace(status_code=status)
    )


def test_a_reminder_goes_to_every_device_the_user_subscribed(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)

    assert send(db, user) == "sent"
    assert push_service.endpoints() == {PHONE, LAPTOP}


def test_the_push_carries_what_the_notification_shows(db, user, push_service):
    subscribe(db, user, PHONE)
    send(db, user)

    [call] = push_service.calls
    assert json.loads(call["data"]) == {
        "title": "Lunch",
        "body": "Nothing logged for lunch yet. Tap to log it.",
        "url": "/log?slot=lunch",
        "tag": "lunch-2026-08-17",
    }
    assert call["subscription_info"] == {
        "endpoint": PHONE,
        "keys": {"p256dh": "p256dh-phone-token", "auth": "auth-phone-token"},
    }
    assert call["vapid_private_key"] == PRIVATE_KEY
    assert call["vapid_claims"]["sub"] == SUBJECT
    # 45 minutes: a reminder that arrives later is about a meal already eaten.
    assert call["ttl"] == 2700


def test_each_push_is_signed_for_its_own_push_service(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    send(db, user)

    audiences = {
        call["subscription_info"]["endpoint"]: call["vapid_claims"]["aud"]
        for call in push_service.calls
    }
    assert audiences == {
        PHONE: "https://fcm.googleapis.com",
        LAPTOP: "https://updates.push.services.mozilla.com",
    }


@pytest.mark.parametrize("status", [404, 410])
def test_a_device_the_push_service_has_forgotten_is_forgotten(db, user, push_service, status):
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    push_service.refusals[PHONE] = refusal(status)

    assert send(db, user) == "sent"
    assert endpoints(db, user) == {LAPTOP}


def test_a_refusal_for_any_other_reason_keeps_the_device(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = refusal(500)

    assert send(db, user) == "failed"
    assert endpoints(db, user) == {PHONE}


def test_an_unreachable_push_service_is_a_failure_not_a_crash(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = requests.ConnectionError("push service unreachable")

    assert send(db, user) == "failed"
    assert endpoints(db, user) == {PHONE}


@pytest.mark.parametrize(
    "error",
    [ValueError("Unsupported elliptic curve point type"), IndexError("index out of range")],
)
def test_keys_that_cannot_be_encrypted_to_fail_only_that_device(db, user, push_service, error):
    # The subscribe route checks only the keys' length, and pywebpush raises a plain
    # ValueError or IndexError for keys that are not a base64url P-256 point.
    subscribe(db, user, PHONE)
    subscribe(db, user, LAPTOP)
    push_service.refusals[PHONE] = error

    assert send(db, user) == "sent"
    assert push_service.endpoints() == {PHONE, LAPTOP}
    assert endpoints(db, user) == {PHONE, LAPTOP}


def test_when_every_device_is_gone_there_is_no_device(db, user, push_service):
    subscribe(db, user, PHONE)
    push_service.refusals[PHONE] = refusal(410)

    assert send(db, user) == "no-device"
    assert endpoints(db, user) == set()


def test_a_user_with_no_device_is_not_pushed(db, user, push_service):
    assert send(db, user) == "no-device"
    assert push_service.calls == []


def test_only_the_users_own_devices_are_pushed(db, user, push_service):
    subscribe(db, user, PHONE)
    subscribe(db, make_user(db, "other"), LAPTOP)

    send(db, user)

    assert push_service.endpoints() == {PHONE}
