"""What cycle data means: bleeds, referrals and coaching, all from logged days.

Symptom-driven, never calendar-driven. Only 13% of cycles are 28 days and the
follicular phase runs anywhere from 10 to 30, so nothing here predicts a phase;
"day 1-3" is counted from bleeding the user actually logged.
"""

import datetime

from app.cycle.rules import (
    Bleed,
    Day,
    Screening,
    bleed_day,
    bleeds,
    coaching,
    last_period_start,
    referral_reason,
)

TODAY = datetime.date(2026, 8, 17)


def day(offset: int, flow: str | None = None, *symptoms: str) -> Day:
    return Day(TODAY + datetime.timedelta(days=offset), flow, frozenset(symptoms))


def bleed(start: int, length: int, flow: str = "medium") -> list[Day]:
    return [day(start + i, flow) for i in range(length)]


def screening(**answers: bool) -> Screening:
    fields = ("soaks_within_two_hours", "longer_than_seven_days", "large_clots", "flooding")
    return Screening(TODAY, **{field: answers.get(field, False) for field in fields})


def ids(days: list[Day], today: datetime.date = TODAY) -> list[str]:
    return [note.id for note in coaching(days, today)]


# --- bleeds -----------------------------------------------------------------------------------


def test_consecutive_bleeding_days_are_one_bleed():
    one_day = datetime.timedelta(days=1)
    assert bleeds(bleed(0, 5)) == [Bleed(TODAY, TODAY + 4 * one_day)]


def test_a_day_without_bleeding_ends_a_bleed():
    assert len(bleeds([day(0, "light"), day(2, "light")])) == 2


def test_a_symptom_on_its_own_is_not_bleeding():
    assert bleeds([day(0, None, "cramps")]) == []


def test_the_last_period_started_on_the_first_day_of_the_latest_bleed():
    assert last_period_start([*bleed(-30, 5), *bleed(-2, 3)]) == TODAY - datetime.timedelta(days=2)


def test_a_bleed_logged_today_is_on_day_one():
    assert bleed_day(bleed(0, 1), TODAY) == 1


def test_a_bleed_logged_until_yesterday_is_still_current():
    # Today's log may simply not be in yet.
    assert bleed_day(bleed(-2, 2), TODAY) == 3


def test_a_bleed_that_ended_days_ago_is_not_current():
    assert bleed_day(bleed(-5, 3), TODAY) is None


def test_nothing_is_predicted_from_a_period_a_cycle_ago():
    # 28 days after the last period is when a calendar app would say "day 1".
    assert bleed_day(bleed(-28, 5), TODAY) is None


# --- referral ---------------------------------------------------------------------------------


def test_no_referral_without_a_reason():
    assert referral_reason(bleed(-3, 5), None, TODAY) is None


def test_heavy_flow_on_its_own_is_not_a_referral():
    """A self-rated "heavy" is not one of the validated questions. Treating it as
    one would refer most people on their heaviest day and teach them to ignore it."""
    assert referral_reason(bleed(-3, 5, "heavy"), None, TODAY) is None


def test_a_yes_on_the_screening_refers():
    reason = referral_reason([], screening(soaks_within_two_hours=True), TODAY)
    assert "two hours" in reason


def test_every_yes_is_named():
    reason = referral_reason([], screening(large_clots=True, flooding=True), TODAY)
    assert "clots" in reason
    assert "flooding" in reason


def test_all_no_answers_do_not_refer():
    assert referral_reason([], screening(), TODAY) is None


def test_more_than_seven_days_of_bleeding_refers():
    assert "8 days in a row" in referral_reason(bleed(-10, 8), None, TODAY)


def test_seven_days_of_bleeding_does_not():
    assert referral_reason(bleed(-10, 7), None, TODAY) is None


def test_a_long_bleed_months_ago_is_not_raised_again():
    assert referral_reason(bleed(-200, 9), None, TODAY) is None


def test_the_reason_is_whole_sentences():
    # The screen splices it between "Please see a clinician." and its own copy.
    reason = referral_reason(bleed(-10, 8), screening(flooding=True), TODAY)
    assert reason.endswith(".")
    assert reason[0].isupper()


# --- coaching ---------------------------------------------------------------------------------


def test_coffee_timing_and_calcium_always_apply():
    assert ids([]) == ["coffee-timing", "calcium"]


def test_vitamin_c_pairing_follows_a_logged_bleed():
    assert "vitamin-c" in ids(bleed(-3, 3))


def test_vitamin_c_pairing_fades_a_week_after_it():
    assert "vitamin-c" not in ids(bleed(-14, 5))


def test_ginger_and_fenugreek_follow_cramps_on_days_one_to_three():
    days = [day(-1, "medium", "cramps"), day(0, "heavy")]
    assert ids(days) == ["coffee-timing", "vitamin-c", "ginger", "fenugreek", "calcium"]


def test_not_on_day_four():
    days = [day(-3, "medium", "cramps"), day(-2, "heavy"), day(-1, "medium"), day(0, "light")]
    assert "ginger" not in ids(days)


def test_not_without_cramps():
    assert "ginger" not in ids(bleed(-1, 2))


def test_cramps_outside_a_bleed_do_not_bring_ginger():
    assert "ginger" not in ids([day(0, None, "cramps")])


def test_the_calcium_note_names_the_pms_symptoms_logged():
    calcium = coaching([day(-5, None, "bloating", "low_mood")], TODAY)[-1]
    assert "bloating and low mood" in calcium.body


def test_every_note_carries_its_evidence_grade():
    notes = coaching([day(-1, "medium", "cramps"), day(0, "heavy")], TODAY)
    grades = {note.id: note.evidence for note in notes}

    assert grades == {
        "coffee-timing": "strong",
        "vitamin-c": "mechanistic",
        "ginger": "moderate",
        "fenugreek": "low",
        "calcium": "moderate",
    }


def test_food_is_never_offered_as_a_substitute_for_treatment():
    ginger = next(n for n in coaching([day(0, "heavy", "cramps")], TODAY) if n.id == "ginger")
    assert "ibuprofen" in ginger.body
    assert "not a substitute for treatment" in ginger.body


def test_logged_pms_symptoms_point_to_a_clinician_not_only_to_calcium():
    # Severe PMS and PMDD low mood have effective treatment; calcium is not it.
    calcium = coaching([day(-5, None, "low_mood")], TODAY)[-1]
    assert "clinician" in calcium.body
    assert "not a substitute" in calcium.body


def test_the_calcium_note_without_symptoms_stays_plain():
    assert "clinician" not in coaching([], TODAY)[-1].body


def test_no_note_mentions_cravings_or_eating_more():
    # The chocolate-craving script is largely an American cultural artefact, and
    # "eat more in the luteal phase" manufactures the pattern that seems to prove it.
    notes = coaching([day(-1, "medium", "cramps", "bloating"), day(0, "heavy")], TODAY)
    for note in notes:
        text = f"{note.title} {note.body}".lower()
        assert "chocolate" not in text
        assert "craving" not in text
        assert "eat more" not in text
