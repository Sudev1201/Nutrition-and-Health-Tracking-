import pytest

from app.nutrition_core.conditions import apply_conditions
from app.nutrition_core.energy import Body
from app.nutrition_core.targets import ReferenceValue, build_targets

REFERENCES = {
    "sodium": ReferenceValue(ear=None, rda=None, ai=2000),
    "potassium": ReferenceValue(ear=None, rda=None, ai=3510),
    "calcium": ReferenceValue(ear=800, rda=1000, ai=None),
    "vitamin_k": ReferenceValue(ear=None, rda=None, ai=120),
}
UPPER_LIMITS = {"calcium": 2500.0}

MAN = Body(sex="male", age=40, weight_kg=70.0, activity="moderate")


def overlay(conditions=(), medications=()):
    base = build_targets(
        MAN,
        goal="maintain",
        pace=None,
        cereal_dominant=False,
        references=REFERENCES,
        upper_limits=UPPER_LIMITS,
    )
    return base, apply_conditions(base, conditions=list(conditions), medications=list(medications))


def test_no_conditions_leaves_the_targets_alone():
    base, result = overlay()

    assert result.targets["sodium"].rda == base["sodium"].rda
    assert result.warnings == []


# Hypertension is the one case that moves sodium off the ICMR baseline.
def test_hypertension_tightens_sodium():
    _, result = overlay(conditions=["hypertension"])

    assert result.targets["sodium"].rda == 1500


def test_high_cholesterol_caps_saturated_fat_at_seven_percent_of_energy():
    base, result = overlay(conditions=["high_cholesterol"])
    energy = base["energy"].rda

    assert result.targets["saturated_fat"].rda == pytest.approx(energy * 0.07 / 9, abs=0.1)


def test_high_cholesterol_is_tighter_than_the_baseline():
    base, result = overlay(conditions=["high_cholesterol"])

    assert result.targets["saturated_fat"].rda < base["saturated_fat"].rda


def test_high_cholesterol_sets_a_dietary_cholesterol_ceiling():
    _, result = overlay(conditions=["high_cholesterol"])

    assert result.targets["cholesterol"].rda == 200
    assert result.targets["cholesterol"].kind == "ceiling"


# RSSDI's absolute 25-40 g/day band acts as a floor under the per-calorie figure.
def test_diabetes_applies_an_absolute_fibre_floor():
    _, result = overlay(conditions=["type2_diabetes"])

    assert result.targets["fibre"].rda >= 25


def test_diabetes_never_lowers_fibre_below_what_energy_already_requires():
    base, result = overlay(conditions=["type2_diabetes"])

    assert result.targets["fibre"].rda >= base["fibre"].rda


def test_diabetes_caps_added_sugar():
    _, result = overlay(conditions=["type2_diabetes"])

    assert result.targets["free_sugar"].rda <= 25


"""
Hypertension and symptomatic hypotension give opposite sodium instructions. The
spec forbids averaging them: the engine must surface a conflict for clinician
review instead, leaving the ICMR baseline in place.
"""


def test_opposite_blood_pressure_conditions_raise_a_conflict():
    _, result = overlay(conditions=["hypertension", "hypotension"])

    assert any(warning.kind == "condition-conflict" for warning in result.warnings)


def test_a_conflict_leaves_sodium_at_the_baseline_rather_than_averaging():
    base, result = overlay(conditions=["hypertension", "hypotension"])

    assert result.targets["sodium"].rda == base["sodium"].rda


def test_opposite_thyroid_conditions_raise_a_conflict():
    _, result = overlay(conditions=["hypothyroidism", "hyperthyroidism"])

    assert any(warning.kind == "condition-conflict" for warning in result.warnings)


"""
Raising potassium is actively unsafe on an ACE inhibitor, ARB or potassium-
sparing diuretic. Hypertension would otherwise trigger exactly that advice, so
the drug has to suppress it and flag for clinician review.
"""


def test_an_ace_inhibitor_suppresses_the_potassium_push_that_hypertension_triggers():
    _, without = overlay(conditions=["hypertension"])
    _, with_drug = overlay(
        conditions=["hypertension"], medications=[("Ramipril", "08:00")]
    )

    assert with_drug.targets["potassium"].rda < without.targets["potassium"].rda


def test_an_ace_inhibitor_flags_potassium_for_clinician_review():
    _, result = overlay(conditions=["hypertension"], medications=[("Ramipril", "08:00")])

    assert any("potassium" in warning.message.lower() for warning in result.warnings)


"""
On warfarin the goal is day-to-day *consistency* of vitamin K, not averaging it
across days. Compensation must be switched off for that nutrient entirely.
"""


def test_warfarin_disables_vitamin_k_compensation():
    _, result = overlay(medications=[("Warfarin", "20:00")])

    assert "vitamin_k" in result.compensation_disabled


def test_vitamin_k_compensation_is_on_without_warfarin():
    _, result = overlay()

    assert result.compensation_disabled == frozenset()


def test_levothyroxine_produces_a_medication_timing_note():
    _, result = overlay(
        conditions=["hypothyroidism"], medications=[("Levothyroxine", "07:00")]
    )

    timing = [w for w in result.warnings if w.kind == "medication-timing"]
    assert timing and "07:00" in timing[0].message
