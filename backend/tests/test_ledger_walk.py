"""The compensation ledger's walk: one pass that Today and the weekly report share.

The fixture dish is 150 kcal, 4 g protein and 30 mg calcium per 100 g, and
carries nothing else. The profile is the reference man: calcium 1,000 mg (EAR
800), protein 0.83 g per kg of his 65 kg, energy from the formula. Each carry
day may take at most 30% of a target, for two days.

Dates run relative to the real today, because a profile save records a weigh-in
dated today, and a recalibration step can only be taken from today.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.user import User
from app.nutrition_core.energy import Body, energy_target
from app.targets import service as targets
from app.weight import service as weight
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


# The day most tests log on: both of its carry days land before today.
SOURCE = days_ago(3)


def after(day: datetime.date, n: int) -> datetime.date:
    return day + datetime.timedelta(days=n)


def formula(weight_kg: float) -> float:
    body = Body(sex="male", age=25, weight_kg=weight_kg, activity="sedentary")
    return energy_target(body, goal="maintain", pace=None)


def signed_in_user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def user(signed_in, reference_data, db) -> User:
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return signed_in_user(db)


def log_rice(api, dish, on_date: datetime.date, grams: float) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(on_date), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": grams, "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


def walk(db, user, start: datetime.date, end: datetime.date, as_of=None):
    context = targets.load_context(db, user, TODAY)
    return targets.walk_ledger(db, user, context, start, end, as_of)


def take_a_step(db, user) -> None:
    """Three weeks of steady gain on a maintain goal: a -210 kcal step, from today.

    Four weigh-ins, because a step needs two consecutive readings to agree: 0.5
    kg/week as of today, and as of last week's weigh-in.
    """
    weight.record_weigh_in(db, user, days_ago(21), 64.5)
    weight.record_weigh_in(db, user, days_ago(14), 65.0)
    weight.record_weigh_in(db, user, days_ago(7), 65.5)
    step = weight.record_weigh_in(db, user, TODAY, 66.0)
    # Checked for None first, so a missing step fails here as an assertion, not
    # later as an AttributeError that looks like the expected load_context failure.
    assert step is not None and step.offset_kcal == -210.0


def row(resolved, code: str):
    return next(n for n in resolved.nutrients if n.code == code)


# --- the context ---------------------------------------------------------------


def test_there_is_no_context_without_a_profile(signed_in, db):
    assert targets.load_context(db, signed_in_user(db), TODAY) is None


# --- which days are tracked ----------------------------------------------------


def test_the_walk_records_every_day_from_start_to_end(db, user):
    ledger = walk(db, user, SOURCE, after(SOURCE, 2))
    assert sorted(ledger.days) == [SOURCE, after(SOURCE, 1), after(SOURCE, 2)]


def test_a_day_with_nothing_logged_is_untracked(db, user):
    day = walk(db, user, SOURCE, SOURCE).days[SOURCE]

    assert day.tracked is False
    assert day.consumed == {}
    assert day.expired_shortfall == {}
    # It still has targets: the report draws them.
    assert day.base["calcium"] == 1000
    assert day.effective["calcium"] == 1000


@pytest.mark.parametrize("as_of_lead", [0, 1])
def test_a_day_on_or_after_as_of_is_untracked(db, user, signed_in, reference_data, as_of_lead):
    """A day still being eaten is part of a day: it neither carries nor expires."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE, as_of=SOURCE - datetime.timedelta(days=as_of_lead))
    day = ledger.days[SOURCE]

    assert day.tracked is False
    assert day.consumed == {}
    assert day.expired_shortfall == {}
    assert ledger.carried == {}


def test_a_day_before_as_of_has_ended(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, SOURCE, SOURCE, as_of=after(SOURCE, 1)).days[SOURCE]

    assert day.tracked is True
    assert day.consumed["calcium"] == pytest.approx(15.0)


# --- what expires --------------------------------------------------------------


def test_a_protein_shortfall_expires_whole(db, user, signed_in, reference_data):
    """Protein has no storage pool: nothing is carried, so the whole shortfall expires."""
    log_rice(signed_in, reference_data, SOURCE, 50)  # 2 g of protein

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_shortfall["protein"] == pytest.approx(65 * 0.83 - 2.0)
    assert all("protein" not in amounts for amounts in ledger.carried.values())


def test_a_shortfall_beyond_the_cap_expires(db, user, signed_in, reference_data):
    # 15 mg of calcium is 985 mg short. Two days at 30% of 1,000 mg carry 600 mg;
    # the other 385 mg is never made up.
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, SOURCE, SOURCE).days[SOURCE]

    assert day.expired_shortfall["calcium"] == pytest.approx(385.0)
    # Energy caps the same way, at 30% of its own target: 75 kcal eaten, 60% carried.
    assert day.expired_shortfall["energy"] == pytest.approx(0.4 * formula(65.0) - 75.0)


def test_a_shortfall_inside_the_cap_is_carried_whole(db, user, signed_in, reference_data):
    # 900 mg of calcium is 100 mg short: 50 mg a day, well inside the cap.
    log_rice(signed_in, reference_data, SOURCE, 3000)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_shortfall["calcium"] == pytest.approx(0.0, abs=1e-9)
    assert ledger.carried[after(SOURCE, 1)]["calcium"] == pytest.approx(50.0)


def test_a_harmful_surplus_beyond_the_cap_expires(db, user, signed_in, reference_data):
    # 4,500 kcal. Each of the next two days is lowered by 30% of the target; the
    # rest of the surplus is recorded as expired, in its own direction.
    log_rice(signed_in, reference_data, SOURCE, 3000)
    target = formula(65.0)

    ledger = walk(db, user, SOURCE, SOURCE)
    day = ledger.days[SOURCE]

    assert day.expired_surplus["energy"] == pytest.approx(4500.0 - 1.6 * target)
    assert "energy" not in day.expired_shortfall
    assert ledger.carried[after(SOURCE, 1)]["energy"] == pytest.approx(-0.3 * target)


def test_an_excreted_surplus_neither_carries_nor_expires(db, user, signed_in, reference_data):
    # 120 g of protein is over the target, but the body has nothing to rebalance.
    log_rice(signed_in, reference_data, SOURCE, 3000)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.days[SOURCE].expired_surplus.get("protein", 0.0) == 0.0
    assert "protein" not in ledger.carried[after(SOURCE, 1)]


def test_an_unmeasured_nutrient_neither_carries_nor_expires(db, user, signed_in, reference_data):
    """The fixture dish has no potassium row: its zero is silence, not a shortfall."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE)
    day = ledger.days[SOURCE]

    assert "potassium" not in day.consumed
    assert "potassium" not in day.expired_shortfall
    assert all("potassium" not in amounts for amounts in ledger.carried.values())
    assert day.effective["potassium"] == 3510


# --- what is carried -----------------------------------------------------------


def test_carries_landing_after_the_walk_are_kept(db, user, signed_in, reference_data):
    """The day after a walk is the day Today asks about, so its carries must survive."""
    log_rice(signed_in, reference_data, SOURCE, 50)

    ledger = walk(db, user, SOURCE, SOURCE)

    assert ledger.carried[after(SOURCE, 1)]["calcium"] == pytest.approx(300.0)
    assert ledger.carried[after(SOURCE, 2)]["calcium"] == pytest.approx(300.0)
    assert ledger.sources[after(SOURCE, 1)]["calcium"] == SOURCE
    assert ledger.sources[after(SOURCE, 2)]["calcium"] == SOURCE


def test_a_carry_raises_the_next_walked_days_target(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    next_day = walk(db, user, SOURCE, after(SOURCE, 1)).days[after(SOURCE, 1)]

    assert next_day.carried_in["calcium"] == pytest.approx(300.0)
    assert next_day.carried_from["calcium"] == SOURCE
    assert next_day.base["calcium"] == 1000
    assert next_day.effective["calcium"] == pytest.approx(1300.0)
    assert "protein" not in next_day.carried_in
    # Nothing was logged on it, so what it was handed simply lapses.
    assert next_day.tracked is False
    assert next_day.expired_shortfall == {}


def test_the_walk_starts_from_a_clean_slate(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    day = walk(db, user, after(SOURCE, 1), after(SOURCE, 1)).days[after(SOURCE, 1)]

    assert day.carried_in == {}
    assert day.effective["calcium"] == 1000


# --- resolve_day reads the walk ------------------------------------------------


def test_resolve_day_reads_its_carries_from_the_walk(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    calcium = row(targets.resolve_day(db, user, after(SOURCE, 1)), "calcium")

    assert calcium.carried_in == pytest.approx(300.0)
    assert calcium.target_effective == pytest.approx(1300.0)
    assert calcium.carried_from == SOURCE.strftime("%A")


def test_resolve_day_hands_as_of_to_the_walk(db, user, signed_in, reference_data):
    log_rice(signed_in, reference_data, SOURCE, 50)

    calcium = row(targets.resolve_day(db, user, after(SOURCE, 1), as_of=SOURCE), "calcium")

    assert calcium.carried_in == 0
    assert calcium.target_effective == pytest.approx(1000.0)


# --- each day at its own recalibration offset ----------------------------------


def test_base_targets_follow_the_offset_in_force_on_each_day(db, user):
    take_a_step(db, user)
    context = targets.load_context(db, user, TODAY)
    stepped = formula(66.0) - 210.0

    today = targets.base_targets_on(db, user, context, TODAY)
    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    assert today["energy"] == pytest.approx(stepped)
    assert yesterday["energy"] == pytest.approx(formula(66.0))
    # Thiamine is energy-scaled (1.4 mg sedentary), so the step moves it too.
    assert today["thiamine"] == pytest.approx(1.4 * stepped / formula(66.0))
    assert yesterday["thiamine"] == pytest.approx(1.4)
    # Protein is per kilogram of the body, and no offset moves it.
    assert today["protein"] == pytest.approx(66.0 * 0.83)
    assert yesterday["protein"] == pytest.approx(66.0 * 0.83)


def test_the_context_date_does_not_set_another_days_offset(db, user):
    take_a_step(db, user)
    context = targets.load_context(db, user, days_ago(1))

    today = targets.base_targets_on(db, user, context, TODAY)
    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    assert today["energy"] == pytest.approx(formula(66.0) - 210.0)
    assert yesterday["energy"] == pytest.approx(formula(66.0))


def test_a_target_a_condition_set_keeps_the_context_dates_figure(signed_in, reference_data, db):
    profile = {**PROFILE, "conditions": ["high_cholesterol"]}
    assert signed_in.put("/profile", json=profile).status_code == 200
    user = signed_in_user(db)
    take_a_step(db, user)
    context = targets.load_context(db, user, TODAY)

    yesterday = targets.base_targets_on(db, user, context, days_ago(1))

    # High cholesterol sets saturated fat at 7% of the context date's energy. The
    # offset is not all that moved it, so it is not rebuilt at yesterday's.
    assert yesterday["saturated_fat"] == pytest.approx((formula(66.0) - 210.0) * 0.07 / 9)
    # Total fat, which no condition touches, follows yesterday's own energy.
    assert yesterday["fat"] == pytest.approx(formula(66.0) * 0.25 / 9)


def test_the_walk_costs_each_day_at_its_own_offset(db, user, signed_in, reference_data):
    """Yesterday was eaten exactly at its own, pre-step, target. Today's step must
    not turn that into a surplus."""
    take_a_step(db, user)
    log_rice(signed_in, reference_data, days_ago(1), formula(66.0) / 150.0 * 100.0)

    ledger = walk(db, user, days_ago(1), TODAY)
    yesterday = ledger.days[days_ago(1)]
    today = ledger.days[TODAY]

    assert yesterday.base["energy"] == pytest.approx(formula(66.0))
    assert yesterday.expired_surplus.get("energy", 0.0) == pytest.approx(0.0, abs=1e-6)
    assert today.base["energy"] == pytest.approx(formula(66.0) - 210.0)
    assert today.carried_in.get("energy", 0.0) == pytest.approx(0.0, abs=1e-6)
