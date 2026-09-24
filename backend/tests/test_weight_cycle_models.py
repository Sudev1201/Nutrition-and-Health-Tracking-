"""Where a day is the unit, the database holds one row per day.

Two weigh-ins an hour apart are the same measurement, and two cycle logs for
one date would double a bleed's length -- which is exactly what the >7-day
referral counts. The service upserts; these constraints are the backstop.
"""

import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.user import User
from app.models.weight import CalorieAdjustment, WeightLog

DAY = datetime.date(2026, 8, 17)


@pytest.fixture
def user(db) -> User:
    user = User(google_sub="sub-models", email="models@example.com", name="Models")
    db.add(user)
    db.flush()
    return user


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def test_one_weigh_in_per_day(db, user):
    db.add(WeightLog(user_id=user.id, logged_on=DAY, weight_kg=70.0))
    db.flush()
    refused(db, WeightLog(user_id=user.id, logged_on=DAY, weight_kg=70.4))


def test_one_calorie_adjustment_per_day(db, user):
    db.add(
        CalorieAdjustment(
            user_id=user.id, effective_from=DAY, kind="step", offset_kcal=-210.0, reason="x"
        )
    )
    db.flush()
    refused(
        db,
        CalorieAdjustment(
            user_id=user.id, effective_from=DAY, kind="reset", offset_kcal=0.0, reason="y"
        ),
    )


def test_one_cycle_settings_row_per_user(db, user):
    db.add(CycleSettings(user_id=user.id, enabled=True))
    db.flush()
    refused(db, CycleSettings(user_id=user.id, enabled=False))


def test_cycle_tracking_is_off_by_default(db, user):
    settings = CycleSettings(user_id=user.id)
    db.add(settings)
    db.flush()
    assert settings.enabled is False


def test_one_flow_per_day(db, user):
    db.add(CycleLog(user_id=user.id, logged_on=DAY, flow="medium"))
    db.flush()
    refused(db, CycleLog(user_id=user.id, logged_on=DAY, flow="heavy"))


def test_a_day_holds_several_symptoms_but_each_once(db, user):
    db.add_all(
        [
            CycleSymptom(user_id=user.id, logged_on=DAY, symptom="cramps"),
            CycleSymptom(user_id=user.id, logged_on=DAY, symptom="bloating"),
        ]
    )
    db.flush()
    refused(db, CycleSymptom(user_id=user.id, logged_on=DAY, symptom="cramps"))


def test_one_set_of_screening_answers_per_day(db, user):
    db.add(CycleScreening(user_id=user.id, answered_on=DAY))
    db.flush()
    refused(db, CycleScreening(user_id=user.id, answered_on=DAY, flooding=True))
