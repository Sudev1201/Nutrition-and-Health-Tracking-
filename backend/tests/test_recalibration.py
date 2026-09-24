"""Weight-driven recalibration: the arithmetic, and the bounds the spec requires.

The reference man throughout is 25 y, 65 kg and sedentary: formula target 2,105.3
kcal on "maintain", uncorrected FAO/WHO/UNU BMR 1,670.9 kcal.
"""

import datetime

import pytest

from app.nutrition_core.energy import Body, basal_metabolic_rate, energy_target
from app.nutrition_core.recalibration import (
    MAX_OFFSET_SHARE,
    WeighIn,
    expected_rate,
    lowest_target,
    next_step,
    observed_rate,
    recalibrated_energy,
    smoothed_weight,
    trend_note,
    trend_points,
)

MAN = Body(sex="male", age=25, weight_kg=65.0, activity="sedentary")
WOMAN = Body(sex="female", age=25, weight_kg=55.0, activity="sedentary")
OLDER_WOMAN = Body(sex="female", age=70, weight_kg=42.0, activity="sedentary")
HEAVY_MAN = Body(sex="male", age=45, weight_kg=80.0, activity="moderate")

DAY0 = datetime.date(2026, 8, 3)


def weekly(*weights: float) -> list[WeighIn]:
    return [WeighIn(DAY0 + datetime.timedelta(weeks=i), kg) for i, kg in enumerate(weights)]


# --- smoothing and the trend ----------------------------------------------------------------


def test_smoothing_averages_the_last_three_weigh_ins():
    assert smoothed_weight(weekly(74.8, 74.9, 74.4, 74.1, 74.2)) == pytest.approx(74.233, abs=1e-3)


def test_smoothing_uses_what_there_is_before_the_third_weigh_in():
    assert smoothed_weight(weekly(70.0)) == 70.0


def test_there_is_no_smoothed_weight_before_the_first_weigh_in():
    assert smoothed_weight([]) is None


def test_the_observed_rate_is_the_fitted_slope_in_kg_per_week():
    assert observed_rate(weekly(70.0, 70.5, 71.0)) == pytest.approx(0.5)


def test_two_weigh_ins_are_not_a_trend():
    assert observed_rate(weekly(70.0, 71.0)) is None


def test_three_weigh_ins_inside_two_weeks_are_not_a_trend():
    points = [
        WeighIn(DAY0, 70.0),
        WeighIn(DAY0 + datetime.timedelta(days=6), 70.5),
        WeighIn(DAY0 + datetime.timedelta(days=13), 71.0),
    ]
    assert observed_rate(points) is None


def test_the_trend_reads_the_last_four_weeks_only():
    history = weekly(80.0, 70.0, 70.0, 70.0, 70.0, 70.0)
    points = trend_points(history, as_of=DAY0 + datetime.timedelta(weeks=5), since=None)
    assert [p.weight_kg for p in points] == [70.0] * 5


def test_the_trend_restarts_at_the_last_step():
    history = weekly(70.0, 70.5, 71.0, 71.5)
    points = trend_points(
        history,
        as_of=DAY0 + datetime.timedelta(weeks=3),
        since=DAY0 + datetime.timedelta(weeks=2),
    )
    assert [p.weight_kg for p in points] == [71.0, 71.5]


# --- the expected trajectory ----------------------------------------------------------------


def test_maintaining_expects_no_change():
    assert expected_rate(MAN, "maintain", None) == 0.0


def test_a_steady_gain_expects_half_a_kilo_a_week():
    assert expected_rate(MAN, "gain", "steady") == pytest.approx(0.5)


def test_a_clamped_loss_expects_what_the_real_deficit_delivers():
    # A steady loss names 0.5 kg/week, but the BMR clamp leaves him a 434 kcal/day
    # deficit and her 357. Holding them to 0.5 would read an on-track trend as a stall.
    assert expected_rate(MAN, "lose", "steady") == pytest.approx(-0.395, abs=1e-3)
    assert expected_rate(WOMAN, "lose", "steady") == pytest.approx(-0.324, abs=1e-3)


# --- the bound and the floor ----------------------------------------------------------------


def test_no_offset_leaves_the_formula_exactly_alone():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert recalibrated_energy(MAN, formula, 0.0) == formula


def test_the_offset_is_bounded_to_ten_percent_of_the_formula():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert recalibrated_energy(MAN, formula, -500.0) == pytest.approx(formula * 0.9)
    assert recalibrated_energy(MAN, formula, 500.0) == pytest.approx(formula * 1.1)


def test_the_floor_is_bmr_when_bmr_is_above_the_safe_minimum():
    formula = energy_target(MAN, goal="maintain", pace=None)
    assert lowest_target(MAN, formula) == pytest.approx(basal_metabolic_rate(MAN))


def test_the_floor_is_the_safe_minimum_when_bmr_is_below_it():
    small = Body(sex="female", age=40, weight_kg=42.0, activity="sedentary")  # BMR 1,186.9
    formula = energy_target(small, goal="maintain", pace=None)
    assert lowest_target(small, formula) == 1200.0


def test_a_target_on_the_safe_floor_is_never_pushed_below_it():
    # Lose/gentle for a 70-year-old at 42 kg would be 1,049.9 kcal; the safe floor
    # lifts it to 1,200, and recalibration cannot take it back down.
    formula = energy_target(OLDER_WOMAN, goal="lose", pace="gentle")
    assert formula == 1200.0
    assert lowest_target(OLDER_WOMAN, formula) == pytest.approx(formula)
    assert recalibrated_energy(OLDER_WOMAN, formula, -100.0) == pytest.approx(formula)


@pytest.mark.parametrize("body", [MAN, WOMAN, OLDER_WOMAN, HEAVY_MAN])
@pytest.mark.parametrize(
    ("goal", "pace"),
    [("lose", "gentle"), ("lose", "steady"), ("maintain", None), ("gain", "steady")],
)
@pytest.mark.parametrize("offset", [-1000.0, -210.0, 0.0, 210.0, 1000.0])
def test_a_recalibrated_target_never_leaves_its_bounds(body, goal, pace, offset):
    formula = energy_target(body, goal=goal, pace=pace)
    kcal = recalibrated_energy(body, formula, offset)

    assert kcal >= basal_metabolic_rate(body) - 1e-9
    assert kcal >= lowest_target(body, formula) - 1e-9
    assert kcal <= formula * (1 + MAX_OFFSET_SHARE) + 1e-9


# --- steps ----------------------------------------------------------------------------------


def test_a_sustained_gain_on_maintain_takes_a_step_down():
    step = next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.5, 66.0))

    # 0.5 kg/week of drift, half-corrected, is 275 kcal: bounded to 10% (210.5 kcal)
    # and kept to whole tens.
    assert step.offset_kcal == -210.0
    assert step.observed_kg_per_week == pytest.approx(0.5)
    assert step.expected_kg_per_week == 0.0


def test_losing_on_maintain_takes_a_step_up():
    step = next_step(MAN, "maintain", None, 0.0, weekly(66.0, 65.7, 65.4))

    # 0.3 kg/week × 1,100 × 0.5 = 165 kcal, truncated to 160.
    assert step.offset_kcal == 160.0


def test_drift_inside_the_tolerance_takes_no_step():
    assert next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.1, 65.2)) is None


def test_steps_do_not_compound_past_the_bound():
    assert next_step(MAN, "maintain", None, -210.0, weekly(66.0, 66.5, 67.0)) is None


def test_a_target_on_the_bmr_floor_takes_no_step_down():
    # A steady loss already clamps him at BMR, so a stalled trend has nowhere to push.
    assert next_step(MAN, "lose", "steady", 0.0, weekly(65.0, 65.0, 65.0)) is None


def test_the_reason_says_what_happened_in_plain_words():
    step = next_step(MAN, "maintain", None, 0.0, weekly(65.0, 65.5, 66.0))

    assert "risen about 0.5 kg a week" in step.reason
    assert "holding steady" in step.reason
    assert "moves down" in step.reason


# --- the note on the weight screen ----------------------------------------------------------


def test_the_note_asks_for_more_weigh_ins_before_there_is_a_trend():
    note = trend_note(MAN, "maintain", None, 0.0, weekly(65.0), stepped_on=None)
    assert "three weigh-ins" in note


def test_the_note_after_a_step_says_when_the_target_moved():
    note = trend_note(MAN, "maintain", None, -210.0, weekly(65.0), stepped_on=DAY0)
    assert "3 August" in note


def test_the_note_explains_a_target_that_cannot_move_further():
    note = trend_note(MAN, "lose", "steady", 0.0, weekly(65.0, 65.0, 65.0), stepped_on=None)
    assert "as far down" in note
    assert "activity level" in note
    # Nothing moved his target -- it sits on the formula's floor -- so it must not say so.
    assert "already moved" not in note
    # Unexplained weight change can be a medical signal, not only a profile typo.
    assert "clinician" in note


def test_the_note_is_plain_when_on_track():
    note = trend_note(MAN, "maintain", None, 0.0, weekly(65.0, 65.1, 65.0), stepped_on=None)
    assert "tracking your goal" in note
