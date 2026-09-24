"""Weigh-ins, the steps they cause, and how `resolve_day` follows them.

Dates run relative to the real today. From Task 5 on, a profile save records a
weigh-in dated today, so a weigh-in on a fixed date in August would be back-dated
-- and a back-dated weigh-in, by design, moves nothing.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.user import User
from app.nutrition_core.energy import Body, basal_metabolic_rate, energy_target
from app.profiles import service as profiles
from app.targets import service as targets
from app.weight import service as weight
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


def nutrient(resolved, code: str):
    return next(n for n in resolved.nutrients if n.code == code)


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return db.scalar(select(User).where(User.email == "track@example.com"))


def gain_half_a_kilo_a_week(db, user):
    """Two weeks of steady gain on a maintain goal: a trend that calls for a step."""
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    weight.record_weigh_in(db, user, days_ago(7), 65.5)
    return weight.record_weigh_in(db, user, TODAY, 66.0)


def test_a_weigh_in_becomes_the_profile_weight(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    assert profiles.get_profile(db, user).weight_kg == 64.2


def test_a_second_weigh_in_the_same_day_replaces_the_first(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    weight.record_weigh_in(db, user, TODAY, 64.6)
    assert [w.weight_kg for w in weight.weigh_ins(db, user) if w.date == TODAY] == [64.6]


def test_a_back_dated_weigh_in_leaves_the_profile_on_the_newest(db, user):
    weight.record_weigh_in(db, user, TODAY, 64.2)
    weight.record_weigh_in(db, user, days_ago(7), 66.0)
    assert profiles.get_profile(db, user).weight_kg == 64.2


def test_a_sustained_gain_on_maintain_takes_a_step_down(db, user):
    step = gain_half_a_kilo_a_week(db, user)

    assert step is not None
    assert step.kind == "step"
    assert step.offset_kcal == -210.0
    assert weight.offset_on(db, user, TODAY) == -210.0


def test_the_step_starts_on_the_day_it_was_taken(db, user):
    gain_half_a_kilo_a_week(db, user)
    # Yesterday keeps the target it had, so its ledger is not re-costed.
    assert weight.offset_on(db, user, days_ago(1)) == 0.0


def test_a_back_dated_weigh_in_takes_no_step(db, user):
    weight.record_weigh_in(db, user, TODAY, 66.0)
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    assert weight.record_weigh_in(db, user, days_ago(7), 65.5) is None
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_resolve_day_follows_the_step(db, user):
    gain_half_a_kilo_a_week(db, user)
    # The formula re-evaluates at the new 66 kg; the step sits on top of it.
    formula = energy_target(
        Body(sex="male", age=25, weight_kg=66.0, activity="sedentary"), goal="maintain", pace=None
    )

    resolved = targets.resolve_day(db, user, TODAY)

    assert nutrient(resolved, "energy").rda == pytest.approx(formula - 210.0)
    # Thiamine is energy-scaled, stored per activity level: 1.4 mg sedentary.
    assert nutrient(resolved, "thiamine").rda == pytest.approx(1.4 * (formula - 210.0) / formula)


def test_a_step_today_does_not_recost_yesterday(db, user, signed_in, reference_data):
    """Yesterday had no offset in force and was eaten exactly at its own target.

    A step taken today must not read that day as a surplus against today's
    stepped figure -- the ledger window must cost each day against the offset
    that was actually in force on it, per the plan's rule against re-costing
    finished days.
    """
    # The pre-step target: the formula at the weight the step will land on
    # (66 kg), with no offset -- exactly what `offset_on(yesterday)` reports.
    formula = energy_target(
        Body(sex="male", age=25, weight_kg=66.0, activity="sedentary"), goal="maintain", pace=None
    )
    grams = formula / 150.0 * 100.0  # reference_data's dish: 150 kcal / 100 g
    response = signed_in.post(
        "/diary/entries",
        json={
            "date": str(days_ago(1)), "slot": "lunch", "food_id": str(reference_data.id),
            "food_kind": "dish", "grams": grams, "is_estimated": False,
        },
    )
    assert response.status_code == 201

    gain_half_a_kilo_a_week(db, user)  # takes the -210 kcal step today

    energy = nutrient(targets.resolve_day(db, user, TODAY), "energy")
    assert energy.carried_in == pytest.approx(0.0, abs=1e-6)


def test_today_says_the_target_was_recalibrated(db, user):
    gain_half_a_kilo_a_week(db, user)
    warnings = targets.resolve_day(db, user, TODAY).warnings

    recalibrated = [w for w in warnings if w.kind == "calorie-recalibrated"]
    assert len(recalibrated) == 1
    assert "210 kcal lower" in recalibrated[0].message


def test_there_is_no_recalibration_note_without_a_step(db, user):
    kinds = [w.kind for w in targets.resolve_day(db, user, TODAY).warnings]
    assert "calorie-recalibrated" not in kinds


def test_protein_follows_the_measured_weight(db, user):
    weight.record_weigh_in(db, user, TODAY, 70.0)
    assert nutrient(targets.resolve_day(db, user, TODAY), "protein").rda == pytest.approx(58.1)


def test_removing_a_weigh_in_removes_the_step_it_caused(db, user):
    gain_half_a_kilo_a_week(db, user)

    assert weight.remove_weigh_in(db, user, TODAY)
    assert weight.offset_on(db, user, TODAY) == 0.0
    assert profiles.get_profile(db, user).weight_kg == 65.5


def test_removing_a_missing_weigh_in_reports_it(db, user):
    assert weight.remove_weigh_in(db, user, days_ago(3)) is False


def test_correcting_todays_weigh_in_re_reads_the_trend(db, user):
    gain_half_a_kilo_a_week(db, user)
    # It was 65.3, not 66.0: 0.15 kg/week is inside the tolerance.
    assert weight.record_weigh_in(db, user, TODAY, 65.3) is None
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_filling_in_a_missed_week_takes_no_step(db, user):
    weight.remove_weigh_in(db, user, TODAY)  # the onboarding weigh-in, from Task 5 on
    weight.record_weigh_in(db, user, days_ago(21), 65.0)
    weight.record_weigh_in(db, user, days_ago(14), 65.5)
    # The newest weigh-in, but dated a week ago: a step from then would re-cost
    # six finished days. It fills history, and today's weigh-in will read it.
    assert weight.record_weigh_in(db, user, days_ago(7), 66.0) is None
    assert weight.offset_on(db, user, days_ago(1)) == 0.0


def post_a_typo_behind_a_step(db, user):
    """56.0 was meant as 66.0: the typo alone reads as 5 kg/week of gain."""
    weight.record_weigh_in(db, user, days_ago(14), 56.0)
    weight.record_weigh_in(db, user, days_ago(7), 66.1)
    assert weight.record_weigh_in(db, user, TODAY, 66.0).offset_kcal == -210.0


def test_correcting_the_typo_a_step_was_read_from_removes_it(db, user):
    post_a_typo_behind_a_step(db, user)
    assert weight.record_weigh_in(db, user, days_ago(14), 66.0) is None  # a flat trend
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_removing_the_typo_a_step_was_read_from_removes_it(db, user):
    post_a_typo_behind_a_step(db, user)
    assert weight.remove_weigh_in(db, user, days_ago(14))  # two left: not a trend
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_a_new_weigh_in_outside_the_steps_reading_leaves_it(db, user):
    gain_half_a_kilo_a_week(db, user)
    weight.record_weigh_in(db, user, days_ago(35), 64.0)
    assert weight.offset_on(db, user, TODAY) == -210.0


def test_a_reset_returns_the_target_to_the_formula(db, user):
    gain_half_a_kilo_a_week(db, user)
    weight.reset_adjustment(db, user, TODAY)
    assert weight.offset_on(db, user, TODAY) == 0.0


def test_the_trend_view_reports_the_step(db, user):
    gain_half_a_kilo_a_week(db, user)
    view = weight.trend(db, user, TODAY)

    assert view.adjustment.delta_kcal == pytest.approx(-210.0)
    assert view.adjustment.since == TODAY
    assert view.observed_kg_per_week is None  # the trend restarts at the step
    assert "last moved" in view.note


def test_the_ledger_never_takes_energy_below_the_floor(db, user, signed_in, reference_data):
    # 4,500 kcal of rice yesterday is a 2,400 kcal surplus. Unfloored, the ledger
    # would lower today by 30% of the target to ~1,474 kcal -- under his BMR.
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(days_ago(1)), "slot": "lunch", "food_id": str(reference_data.id),
            "food_kind": "dish", "grams": 3000, "is_estimated": False,
        },
    )
    energy = nutrient(targets.resolve_day(db, user, TODAY), "energy")

    body = Body(sex="male", age=25, weight_kg=65.0, activity="sedentary")
    assert energy.target_effective == pytest.approx(basal_metabolic_rate(body))
    # The ledger still lowered it -- to the floor, not past it.
    assert energy.carried_in < 0
