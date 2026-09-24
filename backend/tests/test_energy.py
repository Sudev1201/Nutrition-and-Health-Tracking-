"""Golden tests for the energy engine.

ICMR-NIN 2020 publishes six energy figures for its reference adults. They are
the strongest available check that this formula is right, so they are asserted
directly. The tolerance is 12 kcal: the formula reproduces every published value
to within 0.32%, and the residual is ICMR's own rounding, not an error here.
"""

import pytest

from app.nutrition_core.energy import (
    Body,
    basal_metabolic_rate,
    energy_target,
    total_energy_expenditure,
)

TOLERANCE_KCAL = 12

# The reference adults are young adults, so they fall in the 18-30 equation.
REFERENCE_MAN = {"sex": "male", "age": 25, "weight_kg": 65.0}
REFERENCE_WOMAN = {"sex": "female", "age": 25, "weight_kg": 55.0}


@pytest.mark.parametrize(
    ("activity", "published"),
    [("sedentary", 2110), ("moderate", 2710), ("heavy", 3470)],
)
def test_reference_man_matches_icmr(activity, published):
    body = Body(**REFERENCE_MAN, activity=activity)

    assert energy_target(body, goal="maintain", pace=None) == pytest.approx(
        published, abs=TOLERANCE_KCAL
    )


@pytest.mark.parametrize(
    ("activity", "published"),
    [("sedentary", 1660), ("moderate", 2130), ("heavy", 2720)],
)
def test_reference_woman_matches_icmr(activity, published):
    body = Body(**REFERENCE_WOMAN, activity=activity)

    assert energy_target(body, goal="maintain", pace=None) == pytest.approx(
        published, abs=TOLERANCE_KCAL
    )


def test_bmr_uses_the_age_band_equation():
    """FAO/WHO/UNU publishes a different equation per age band, and they do not
    agree at the boundary -- a 34-year-old is not a 25-year-old scaled down."""
    young = basal_metabolic_rate(Body(sex="male", age=25, weight_kg=65, activity="moderate"))
    middle = basal_metabolic_rate(Body(sex="male", age=34, weight_kg=65, activity="moderate"))

    assert young > middle


def test_older_adults_get_the_60_plus_equation():
    middle = basal_metabolic_rate(Body(sex="female", age=50, weight_kg=55, activity="moderate"))
    older = basal_metabolic_rate(Body(sex="female", age=65, weight_kg=55, activity="moderate"))

    assert older != middle


def test_energy_scales_with_weight():
    lighter = energy_target(
        Body(sex="male", age=30, weight_kg=60, activity="moderate"), goal="maintain", pace=None
    )
    heavier = energy_target(
        Body(sex="male", age=30, weight_kg=80, activity="moderate"), goal="maintain", pace=None
    )

    assert heavier > lighter


def test_losing_weight_lowers_the_target():
    body = Body(sex="male", age=30, weight_kg=80, activity="moderate")

    maintain = energy_target(body, goal="maintain", pace=None)
    lose = energy_target(body, goal="lose", pace="steady")

    assert lose < maintain


def test_a_steady_pace_cuts_more_than_a_gentle_one():
    body = Body(sex="male", age=30, weight_kg=80, activity="moderate")

    gentle = energy_target(body, goal="lose", pace="gentle")
    steady = energy_target(body, goal="lose", pace="steady")

    assert steady < gentle


def test_gaining_weight_raises_the_target():
    body = Body(sex="male", age=30, weight_kg=60, activity="moderate")

    maintain = energy_target(body, goal="maintain", pace=None)
    gain = energy_target(body, goal="gain", pace="steady")

    assert gain > maintain


def test_the_target_never_falls_below_basal_metabolic_rate():
    """A small, sedentary person losing weight at a steady pace is where an
    unclamped deficit goes below BMR -- which is not a diet, it is starvation."""
    body = Body(sex="female", age=70, weight_kg=42, activity="sedentary")

    target = energy_target(body, goal="lose", pace="steady")

    assert target >= basal_metabolic_rate(body)


def test_an_unknown_activity_level_is_refused():
    with pytest.raises(ValueError, match="activity"):
        energy_target(
            Body(sex="male", age=30, weight_kg=70, activity="athlete"),
            goal="maintain",
            pace=None,
        )


def test_a_loss_target_never_falls_below_the_safe_floor():
    """1,200 kcal for women and 1,500 for men is the conventional floor for cutting
    calories without medical supervision. BMR alone sits under it for many smaller
    and older people, so the clamp takes the higher of the two."""
    woman = Body(sex="female", age=65, weight_kg=55.0, activity="sedentary")
    man = Body(sex="male", age=65, weight_kg=65.0, activity="sedentary")

    assert energy_target(woman, goal="lose", pace="steady") == 1200.0
    assert energy_target(man, goal="lose", pace="steady") == 1500.0


def test_a_loss_target_never_asks_for_more_than_maintenance():
    """The floor gives way where maintenance itself is lower (1,404.5 kcal here)."""
    body = Body(sex="male", age=70, weight_kg=45.0, activity="sedentary")

    assert energy_target(body, goal="lose", pace="steady") == pytest.approx(
        total_energy_expenditure(body)
    )
