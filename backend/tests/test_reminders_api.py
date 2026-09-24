"""Reminder settings and push subscriptions, over HTTP.

The settings are the profile's own meal-time rows, edited in place, so a
reminder fires at the time the diary shows and the planner plans for. The
devices belong to the user, not the profile: a profile save replaces every
meal-time row, and must never unsubscribe a phone.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.meal_slots import DEFAULT_SLOT_TIMES, SLOTS
from app.models.profile import MealSlotTime
from app.models.push import PushSubscription
from app.models.user import User
from app.profiles import service as profiles
from app.reminders import service as reminders
from tests.test_tracking_api import PROFILE

ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-one"
KEYS = {"p256dh": "B" + "p" * 86, "auth": "a" * 22}

# What a profile saved before meal times existed reminds about: every slot at its
# default time, and the mid-morning snack opt-in.
DEFAULTS = [
    {"slot": "breakfast", "time": "08:00", "weekend_time": None, "reminder_on": True},
    {"slot": "snack1", "time": "11:00", "weekend_time": None, "reminder_on": False},
    {"slot": "lunch", "time": "13:30", "weekend_time": None, "reminder_on": True},
    {"slot": "snack2", "time": "17:00", "weekend_time": None, "reminder_on": True},
    {"slot": "dinner", "time": "20:30", "weekend_time": None, "reminder_on": True},
]


def subscription(endpoint: str = ENDPOINT, **extra) -> dict:
    return {"endpoint": endpoint, "keys": KEYS, **extra}


def meal_times(**changes: dict) -> list[dict]:
    """PROFILE's meal times, with the named slots' fields changed."""
    return [{**item, **changes.get(item["slot"], {})} for item in PROFILE["meal_times"]]


def slot_named(payload: dict, slot: str) -> dict:
    return next(item for item in payload["slots"] if item["slot"] == slot)


def profile_slot(client, slot: str) -> dict:
    """The slot as the profile reads it back, disabled slots included."""
    return slot_named({"slots": client.get("/profile").json()["meal_times"]}, slot)


def turn(client, slot: str, on: bool):
    return client.patch("/settings/reminders", json={"slot": slot, "reminder_on": on})


def unsubscribe(client, endpoint: str = ENDPOINT):
    return client.request("DELETE", "/push/subscriptions", json={"endpoint": endpoint})


def the_row(db) -> PushSubscription:
    return db.scalars(select(PushSubscription).where(PushSubscription.endpoint == ENDPOINT)).one()


def someone_elses_device(db, endpoint: str = ENDPOINT) -> User:
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(PushSubscription(user_id=other.id, endpoint=endpoint, p256dh="q" * 87, auth="b" * 22))
    db.flush()
    return other


@pytest.fixture
def me(signed_in, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def vapid(monkeypatch):
    """A configured server. Set explicitly: a developer's .env may carry real keys."""
    monkeypatch.setattr(settings, "vapid_public_key", "BPublicKeyForTests")
    monkeypatch.setattr(settings, "vapid_private_key", "private-key-for-tests")


# --- settings --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/settings/reminders", None),
        ("PATCH", "/settings/reminders", {"slot": "lunch", "reminder_on": False}),
        ("GET", "/push/public-key", None),
        ("POST", "/push/subscriptions", subscription()),
        ("DELETE", "/push/subscriptions", {"endpoint": ENDPOINT}),
    ],
)
def test_reminder_routes_need_a_session(api_client, method, path, body):
    assert api_client.request(method, path, json=body).status_code == 401


def test_reminder_settings_need_a_profile(signed_in):
    response = signed_in.get("/settings/reminders")

    assert response.status_code == 404
    assert response.json()["detail"] == "Complete your profile first"
    assert turn(signed_in, "lunch", False).status_code == 404


def test_the_settings_are_the_profiles_meal_times(signed_in):
    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json() == {
        "slots": PROFILE["meal_times"],
        "devices": 0,
    }


def test_the_slots_come_in_meal_order_not_row_order(signed_in, me, db):
    """The profile's meal times read back in primary-key order, and the keys are random."""
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})
    for n, slot in enumerate(reversed(SLOTS), start=1):
        db.add(
            MealSlotTime(
                id=uuid.UUID(int=n),
                user_id=me.id,
                slot=slot,
                usual_time=datetime.time.fromisoformat(DEFAULT_SLOT_TIMES[slot]),
            )
        )
    db.flush()
    assert [row.slot for row in profiles.get_meal_times(db, me)] == list(reversed(SLOTS))

    slots = signed_in.get("/settings/reminders").json()["slots"]

    assert [item["slot"] for item in slots] == list(SLOTS)


def test_a_weekend_time_comes_through(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(breakfast={"weekend_time": "09:30"})}
    )

    breakfast = slot_named(signed_in.get("/settings/reminders").json(), "breakfast")

    assert breakfast == {
        "slot": "breakfast",
        "time": "08:00",
        "weekend_time": "09:30",
        "reminder_on": True,
    }


def test_a_switched_off_snack_has_no_reminder_to_set(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack2={"is_enabled": False})}
    )

    slots = signed_in.get("/settings/reminders").json()["slots"]

    assert [item["slot"] for item in slots] == ["breakfast", "snack1", "lunch", "dinner"]


def test_a_profile_without_meal_times_reminds_at_the_default_times(signed_in):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    assert signed_in.get("/settings/reminders").json()["slots"] == DEFAULTS


def test_a_reminder_can_be_turned_off(signed_in):
    signed_in.put("/profile", json=PROFILE)

    response = turn(signed_in, "lunch", False)

    assert response.status_code == 200
    assert slot_named(response.json(), "lunch") == {
        "slot": "lunch",
        "time": "13:30",
        "weekend_time": None,
        "reminder_on": False,
    }
    # One setting, on the row the profile reads -- not a copy that could drift.
    assert profile_slot(signed_in, "lunch")["reminder_on"] is False


def test_turning_a_reminder_on_leaves_the_times_alone(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack1={"weekend_time": "11:30"})}
    )

    snack1 = slot_named(turn(signed_in, "snack1", True).json(), "snack1")

    assert snack1 == {
        "slot": "snack1",
        "time": "11:00",
        "weekend_time": "11:30",
        "reminder_on": True,
    }


def test_a_reminder_set_before_meal_times_existed_gets_one_row(signed_in, me, db):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    assert turn(signed_in, "dinner", False).status_code == 200
    # The second call must update the row the first created, not insert another.
    response = turn(signed_in, "dinner", True)

    assert response.status_code == 200
    assert slot_named(response.json(), "dinner") == {
        "slot": "dinner",
        "time": "20:30",
        "weekend_time": None,
        "reminder_on": True,
    }
    rows = db.scalars(select(MealSlotTime).where(MealSlotTime.user_id == me.id)).all()
    assert [(row.slot, row.is_enabled, row.reminder_on) for row in rows] == [("dinner", True, True)]


def test_turning_one_reminder_off_leaves_the_rest_at_their_defaults(signed_in):
    signed_in.put("/profile", json={**PROFILE, "meal_times": []})

    slots = turn(signed_in, "breakfast", False).json()["slots"]

    assert slots == [{**DEFAULTS[0], "reminder_on": False}, *DEFAULTS[1:]]


def test_an_unknown_slot_is_refused(signed_in):
    signed_in.put("/profile", json=PROFILE)
    assert turn(signed_in, "brunch", True).status_code == 422


def test_a_switched_off_snack_cannot_be_given_a_reminder(signed_in):
    signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times(snack2={"is_enabled": False})}
    )

    response = turn(signed_in, "snack2", False)

    assert response.status_code == 422
    assert "switched off" in response.json()["detail"]
    snack2 = profile_slot(signed_in, "snack2")
    assert snack2["is_enabled"] is False
    assert snack2["reminder_on"] is True


def test_a_profile_save_keeps_a_reminder_turned_off_here(signed_in):
    signed_in.put("/profile", json=PROFILE)
    turn(signed_in, "lunch", False)

    # An edit that says nothing about reminders, as the wizard's did until this plan.
    silent = [{k: v for k, v in item.items() if k != "reminder_on"} for item in meal_times()]
    signed_in.put("/profile", json={**PROFILE, "meal_times": silent})

    slots = signed_in.get("/settings/reminders").json()["slots"]
    assert {item["slot"]: item["reminder_on"] for item in slots} == {
        "breakfast": True,
        "snack1": False,
        "lunch": False,
        "snack2": True,
        "dinner": True,
    }


# --- the server's key ------------------------------------------------------------------


def test_the_public_key_is_handed_to_the_browser(signed_in, vapid):
    response = signed_in.get("/push/public-key")

    assert response.status_code == 200
    assert response.json() == {"key": "BPublicKeyForTests"}


@pytest.mark.parametrize("unset", ["vapid_public_key", "vapid_private_key"])
def test_without_both_keys_reminders_are_not_set_up(signed_in, vapid, monkeypatch, unset):
    monkeypatch.setattr(settings, unset, "")

    response = signed_in.get("/push/public-key")

    assert response.status_code == 503
    assert response.json()["detail"] == "Reminders are not set up on this server"


# --- devices ---------------------------------------------------------------------------


def test_subscribing_a_device_counts_it(signed_in):
    signed_in.put("/profile", json=PROFILE)

    response = signed_in.post("/push/subscriptions", json=subscription())

    assert response.status_code == 201
    assert response.json() == {"devices": 1}
    assert signed_in.get("/settings/reminders").json()["devices"] == 1


def test_a_second_browser_is_a_second_device(signed_in):
    signed_in.post("/push/subscriptions", json=subscription())
    response = signed_in.post("/push/subscriptions", json=subscription(f"{ENDPOINT}-laptop"))
    assert response.json() == {"devices": 2}


def test_resubscribing_a_browser_replaces_its_keys(signed_in, db):
    signed_in.post("/push/subscriptions", json=subscription())
    fresh = {"endpoint": ENDPOINT, "keys": {"p256dh": "C" + "r" * 86, "auth": "c" * 22}}

    assert signed_in.post("/push/subscriptions", json=fresh).json() == {"devices": 1}
    row = the_row(db)
    assert (row.p256dh, row.auth) == ("C" + "r" * 86, "c" * 22)


def test_a_browser_subscribed_from_another_account_moves_to_this_one(signed_in, me, db):
    """A shared phone reminds only whoever subscribed it last."""
    other = someone_elses_device(db)

    assert signed_in.post("/push/subscriptions", json=subscription()).json() == {"devices": 1}
    assert the_row(db).user_id == me.id
    assert reminders.device_count(db, other) == 0


def test_only_this_users_devices_are_counted(signed_in, db):
    someone_elses_device(db, f"{ENDPOINT}-theirs")
    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json()["devices"] == 0


def test_a_profile_save_leaves_the_devices_subscribed(signed_in):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/push/subscriptions", json=subscription())

    signed_in.put("/profile", json=PROFILE)

    assert signed_in.get("/settings/reminders").json()["devices"] == 1


def test_subscribing_records_the_browsers_timezone(signed_in):
    signed_in.post("/push/subscriptions", json=subscription(timezone="Europe/London"))
    assert signed_in.get("/auth/me").json()["timezone"] == "Europe/London"


@pytest.mark.parametrize("timezone", ["Not/AZone", "", "../../etc/passwd"])
def test_a_timezone_this_server_cannot_resolve_is_ignored(signed_in, timezone):
    response = signed_in.post("/push/subscriptions", json=subscription(timezone=timezone))

    assert response.status_code == 201
    assert signed_in.get("/auth/me").json()["timezone"] == "Asia/Kolkata"


def test_no_timezone_leaves_the_users_alone(signed_in):
    signed_in.post("/push/subscriptions", json=subscription())
    assert signed_in.get("/auth/me").json()["timezone"] == "Asia/Kolkata"


def test_the_user_agent_is_cut_to_fit(signed_in, db):
    agent = "Mozilla/5.0 " + "x" * 400

    response = signed_in.post(
        "/push/subscriptions", json=subscription(), headers={"User-Agent": agent}
    )

    assert response.status_code == 201
    assert the_row(db).user_agent == agent[:300]


@pytest.mark.parametrize(
    "body",
    [
        # Plain http: the server would POST wherever this points.
        {"endpoint": "http://localhost:8000/admin", "keys": KEYS},
        {"endpoint": ENDPOINT},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "", "auth": "a" * 22}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "p" * 201, "auth": "a" * 22}},
        {"endpoint": ENDPOINT, "keys": {"p256dh": "p" * 87, "auth": "a" * 101}},
    ],
)
def test_a_malformed_subscription_is_refused(signed_in, me, db, body):
    assert signed_in.post("/push/subscriptions", json=body).status_code == 422
    assert reminders.device_count(db, me) == 0


def test_unsubscribing_forgets_the_device(signed_in, me, db):
    signed_in.post("/push/subscriptions", json=subscription())

    assert unsubscribe(signed_in).status_code == 204
    assert reminders.device_count(db, me) == 0


def test_someone_elses_device_cannot_be_unsubscribed(signed_in, db):
    other = someone_elses_device(db)

    assert unsubscribe(signed_in).status_code == 404
    assert reminders.device_count(db, other) == 1


def test_unsubscribing_an_unknown_device_is_not_found(signed_in):
    assert unsubscribe(signed_in).status_code == 404
