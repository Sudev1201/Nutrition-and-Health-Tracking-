"""Push subscriptions, reminder claims and the plan's emphasis, on the migrated schema.

A reminder goes out at most once because the database refuses a second claim on
the same user, date and slot -- not because the sender remembers what it sent.
A phone reminds one person because an endpoint is one row. The runner and the
subscribe route stand on these constraints, so they are tested where they live.
"""

import datetime
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.models.plan import MealPlan
from app.models.push import PushSubscription, ReminderDelivery
from app.models.user import User

DAY = datetime.date(2026, 8, 17)
WEEK = datetime.date(2026, 8, 16)  # a Sunday
ENDPOINT = "https://fcm.googleapis.com/fcm/send/device-one"


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def user(db) -> User:
    return make_user(db, "push")


def device(user: User, endpoint: str = ENDPOINT) -> PushSubscription:
    return PushSubscription(user_id=user.id, endpoint=endpoint, p256dh="p" * 87, auth="a" * 22)


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def rows_of(db, model, user_id: uuid.UUID) -> list:
    return db.scalars(select(model).where(model.user_id == user_id)).all()


def claim(db, user: User, slot: str = "lunch", day: datetime.date = DAY) -> uuid.UUID | None:
    """The runner's claim: the new row's id when this call won the reminder, else None."""
    return db.execute(
        insert(ReminderDelivery)
        .values(user_id=user.id, local_date=day, slot=slot, status="failed")
        .on_conflict_do_nothing(constraint="uq_delivery_user_day_slot")
        .returning(ReminderDelivery.id)
    ).scalar_one_or_none()


def test_an_endpoint_is_one_subscription_whoever_posts_it(db, user):
    db.add(device(user))
    db.flush()
    # The same browser, subscribed from another account, must move -- not duplicate.
    refused(db, device(make_user(db, "other")))


def test_a_user_can_subscribe_several_devices(db, user):
    db.add_all([device(user), device(user, f"{ENDPOINT}-laptop")])
    db.flush()

    rows = rows_of(db, PushSubscription, user.id)
    assert len(rows) == 2
    assert {row.user_agent for row in rows} == {None}


def test_a_reminder_is_claimed_once(db, user):
    assert claim(db, user) is not None
    # A restart, an overlapping cron run or a second instance: each loses the insert.
    assert claim(db, user) is None


def test_each_slot_and_each_day_is_its_own_claim(db, user):
    assert claim(db, user, "lunch", DAY) is not None
    assert claim(db, user, "dinner", DAY) is not None
    assert claim(db, user, "lunch", DAY + datetime.timedelta(days=1)) is not None


def test_one_users_claim_does_not_block_another(db, user):
    assert claim(db, user) is not None
    assert claim(db, make_user(db, "other")) is not None


def test_devices_and_claims_go_with_their_user(db, user):
    user_id = user.id
    db.add(device(user))
    db.flush()
    assert claim(db, user) is not None

    db.delete(user)
    db.flush()

    assert rows_of(db, PushSubscription, user_id) == []
    assert rows_of(db, ReminderDelivery, user_id) == []


def test_a_new_plan_has_no_emphasis(db, user):
    plan = MealPlan(user_id=user.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    assert plan.emphasis == ""


def test_a_plan_stored_before_emphasis_existed_reads_as_none(db, user):
    """The migration's server default is the backfill every existing plan gets."""
    plan_id = uuid.uuid4()
    db.execute(
        text(
            "insert into meal_plans (id, user_id, week_start, seed) "
            "values (:id, :user_id, :week_start, 1)"
        ),
        {"id": plan_id, "user_id": user.id, "week_start": WEEK},
    )
    emphasis = db.scalar(text("select emphasis from meal_plans where id = :id"), {"id": plan_id})
    assert emphasis == ""


def test_meal_logs_are_indexed_by_user_and_day(db):
    indexes = inspect(db.connection()).get_indexes("meal_logs")
    columns = {index["name"]: index["column_names"] for index in indexes}
    assert columns["ix_meal_logs_user_day"] == ["user_id", "logged_on"]
