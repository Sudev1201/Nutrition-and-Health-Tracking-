"""`resolve_day` exposes what the planner needs beyond the targets themselves."""

import datetime

from sqlalchemy import select

from app.models.user import User
from app.targets import service as targets
from tests.test_tracking_api import PROFILE

TODAY = datetime.date(2026, 8, 17)


def _user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


def test_warfarin_marks_vitamin_k_as_held_steady(signed_in, reference_data, db):
    signed_in.put(
        "/profile",
        json={**PROFILE, "medications": [{"name": "Warfarin", "time": "20:00"}]},
    )

    resolved = targets.resolve_day(db, _user(db), TODAY)

    assert resolved.hold_steady == frozenset({"vitamin_k"})


def test_nothing_is_held_steady_without_an_anticoagulant(signed_in, reference_data, db):
    signed_in.put("/profile", json=PROFILE)

    resolved = targets.resolve_day(db, _user(db), TODAY)

    assert resolved.hold_steady == frozenset()
