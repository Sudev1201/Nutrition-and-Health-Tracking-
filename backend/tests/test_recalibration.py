"""Weight-driven recalibration: the arithmetic, and the bounds the spec requires.

The reference man throughout is 25 y, 65 kg and sedentary: formula target 2,105.3
kcal on "maintain", uncorrected FAO/WHO/UNU BMR 1,670.9 kcal. The reference woman
is 25 y, 55 kg and sedentary: 1,658.2 kcal on "maintain", so a 10% bound of 165.8.
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
    previous_trend_points,
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


def readings(*weights: float) -> tuple[list[WeighIn], list[WeighIn]]:
    """The two readings a step is decided on, the newest weigh-in being today's.

    The trend as of the newest weigh-in, and as it stood at the one before it.
    """
    history = weekly(*weights)
    as_of = history[-1].date
    return (
        trend_points(history, as_of=as_of, since=None),
        previous_trend_points(history, as_of=as_of, since=None),
    )


def step_after(body: Body, goal: str, pace: str | None, offset: float, *weights: float):
    points, previous = readings(*weights)
    return next_step(body, goal, pace, offset, points, previous_points=previous)


def note_after(body: Body, goal: str, pace: str | None, offset: float, *weights: float):
    points, previous = readings(*weights)
    return trend_note(body, goal, pace, offset, points, stepped_on=None, previous_points=previous)


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


def test_the_previous_reading_is_the_trend_as_of_the_weigh_in_before_the_newest():
    history = weekly(70.0, 70.5, 71.0, 71.5)
    points = previous_trend_points(history, as_of=DAY0 + datetime.timedelta(weeks=3), since=None)
    assert [p.weight_kg for p in points] == [70.0, 70.5, 71.0]


def test_the_previous_reading_keeps_its_own_four_weeks_and_the_last_step():
    history = weekly(80.0, 70.0, 70.0, 70.0, 70.0, 70.0, 70.0)
    as_of = DAY0 + datetime.timedelta(weeks=6)
    # As of week 5, the four weeks back to week 1: the 80 kg of week 0 is out.
    assert [p.weight_kg for p in previous_trend_points(history, as_of, since=None)] == [70.0] * 5
    # And nothing before the step on week 4.
    since = DAY0 + datetime.timedelta(weeks=4)
    assert [p.date for p in previous_trend_points(history, as_of, since=since)] == [
        since,
        since + datetime.timedelta(weeks=1),
    ]


def test_there_is_no_previous_reading_before_the_second_weigh_in():
    assert previous_trend_points(weekly(70.0), as_of=DAY0, since=None) == []


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
    step = step_after(MAN, "maintain", None, 0.0, 64.5, 65.0, 65.5, 66.0)

    # 0.5 kg/week of drift on both readings, half-corrected, is 275 kcal: bounded
    # to 10% (210.5 kcal) and kept to whole tens.
    assert step.offset_kcal == -210.0
    assert step.observed_kg_per_week == pytest.approx(0.5)
    assert step.expected_kg_per_week == 0.0


def test_losing_on_maintain_takes_a_step_up():
    step = step_after(MAN, "maintain", None, 0.0, 66.3, 66.0, 65.7, 65.4)

    # 0.3 kg/week × 1,100 × 0.5 = 165 kcal, truncated to 160.
    assert step.offset_kcal == 160.0


def test_drift_inside_the_tolerance_takes_no_step():
    assert step_after(MAN, "maintain", None, 0.0, 64.9, 65.0, 65.1, 65.2) is None


def test_steps_do_not_compound_past_the_bound():
    assert step_after(MAN, "maintain", None, -210.0, 65.5, 66.0, 66.5, 67.0) is None


def test_a_target_on_the_bmr_floor_takes_no_step_down():
    # A steady loss already clamps him at BMR, so a stalled trend has nowhere to push.
    assert step_after(MAN, "lose", "steady", 0.0, 65.0, 65.0, 65.0, 65.0) is None


def test_the_reason_says_what_happened_in_plain_words():
    step = step_after(MAN, "maintain", None, 0.0, 64.5, 65.0, 65.5, 66.0)

    assert "risen about 0.5 kg a week" in step.reason
    assert "holding steady" in step.reason
    assert "moves down" in step.reason


def test_a_step_is_sized_from_the_offset_in_force_not_the_one_stored():
    # -300 kcal was stored when the formula was higher; today's bound is 210.5, so
    # -210.5 is what is in force. A 0.3 kg/week loss moves that up by 165 kcal, to
    # -45.5 and so -40 -- not the -300 + 165 = -135 the stored figure would give.
    step = step_after(MAN, "maintain", None, -300.0, 66.3, 66.0, 65.7, 65.4)

    assert step.offset_kcal == -40.0


# --- a step needs the trend confirmed -------------------------------------------------------


def test_a_trend_read_once_takes_no_step():
    # Three weigh-ins are a trend of 0.5 kg/week, but the reading before had two.
    assert step_after(WOMAN, "maintain", None, 0.0, 55.0, 55.5, 56.0) is None


def test_a_sustained_half_a_kilo_a_week_over_four_readings_takes_a_step():
    step = step_after(WOMAN, "maintain", None, 0.0, 55.0, 55.5, 56.0, 56.5)

    # 275 kcal, bounded to her 165.8 and kept to whole tens.
    assert step.offset_kcal == -160.0
    assert step.observed_kg_per_week == pytest.approx(0.5)


def test_one_water_heavy_morning_as_the_newest_weigh_in_takes_no_step():
    # With three weekly points the fitted slope is (last - first) / 2: 0.4 kg/week,
    # from one premenstrual morning. The reading before it had no trend to agree.
    assert step_after(WOMAN, "maintain", None, 0.0, 55.0, 55.0, 55.8) is None


def test_one_water_heavy_morning_is_diluted_by_the_next_weigh_in():
    # 0.08 kg/week once 55.0 follows it -- inside the tolerance -- so the 0.4 of
    # the reading before is never confirmed.
    assert step_after(WOMAN, "maintain", None, 0.0, 55.0, 55.0, 55.8, 55.0) is None


def test_no_weigh_in_of_a_flat_series_with_one_heavy_morning_steps():
    series = (55.0, 55.0, 55.8, 55.0, 55.0, 55.0, 55.0)
    for n in range(1, len(series) + 1):
        assert step_after(WOMAN, "maintain", None, 0.0, *series[:n]) is None, series[:n]


def test_readings_that_disagree_in_direction_take_no_step():
    rising = weekly(55.0, 55.5, 56.0)
    falling = weekly(56.0, 55.5, 55.0)
    assert next_step(WOMAN, "maintain", None, 0.0, rising, previous_points=falling) is None


# --- the note on the weight screen ----------------------------------------------------------


def test_the_note_asks_for_more_weigh_ins_before_there_is_a_trend():
    note = note_after(MAN, "maintain", None, 0.0, 65.0)
    assert "three weigh-ins" in note


def test_the_note_after_a_step_says_when_the_target_moved():
    note = trend_note(
        MAN, "maintain", None, -210.0, weekly(65.0), stepped_on=DAY0, previous_points=[]
    )
    assert "3 August" in note


def test_the_note_explains_a_target_that_cannot_move_further():
    note = note_after(MAN, "lose", "steady", 0.0, 65.0, 65.0, 65.0, 65.0)
    assert "as far down" in note
    assert "activity level" in note
    # Nothing moved his target -- it sits on the formula's floor -- so it must not say so.
    assert "already moved" not in note
    # Unexplained weight change can be a medical signal, not only a profile typo.
    assert "clinician" in note


def test_the_note_is_plain_when_on_track():
    note = note_after(MAN, "maintain", None, 0.0, 65.0, 65.1, 65.0)
    assert "tracking your goal" in note


def test_an_unconfirmed_drift_says_the_next_weigh_in_decides():
    note = note_after(WOMAN, "maintain", None, 0.0, 55.0, 55.0, 55.8)
    assert note == (
        "Your weight has risen about 0.4 kg a week. If your next weigh-in confirms it, "
        "your calorie target will move."
    )


def test_an_unconfirmed_drift_against_a_moving_goal_names_the_goal():
    # "Held steady" alone would not say why a target might move.
    note = note_after(MAN, "gain", "steady", 0.0, 65.0, 65.0, 65.0)
    assert "held steady against a goal of gaining about 0.5 kg a week" in note
    assert "If your next weigh-in confirms it" in note


def test_there_is_no_note_once_both_readings_agree():
    # The step itself explains the move, through the adjustment's reason.
    assert note_after(MAN, "maintain", None, 0.0, 64.5, 65.0, 65.5, 66.0) is None
