import pytest

from app.nutrition_core.energy import Body
from app.nutrition_core.targets import ReferenceValue, build_targets

# Only the rows a test actually reads; the real lookup comes from rda_reference,
# already filtered by sex, age band and activity level.
REFERENCES = {
    "calcium": ReferenceValue(ear=800, rda=1000, ai=None),
    "iron": ReferenceValue(ear=11, rda=19, ai=None),
    "sodium": ReferenceValue(ear=None, rda=None, ai=2000),
    "vitamin_b12": ReferenceValue(ear=2, rda=2.2, ai=None),
    "thiamine": ReferenceValue(ear=1.2, rda=1.4, ai=None),
}

UPPER_LIMITS = {"calcium": 2500.0, "iron": 45.0}

MAN = Body(sex="male", age=25, weight_kg=65.0, activity="sedentary")
WOMAN = Body(sex="female", age=25, weight_kg=55.0, activity="sedentary")


def targets_for(body, cereal_dominant=False, references=None):
    return build_targets(
        body,
        goal="maintain",
        pace=None,
        cereal_dominant=cereal_dominant,
        references=references if references is not None else REFERENCES,
        upper_limits=UPPER_LIMITS,
    )


"""
Protein is weight-based, not looked up: ICMR's published 54.0 g and 45.7 g are
just 0.83 g/kg at the reference weights of 65 kg and 55 kg. Using the table
value for a 90 kg person would under-target them by a third.
"""


def test_protein_matches_icmr_at_the_reference_man_weight():
    assert targets_for(MAN)["protein"].rda == pytest.approx(54.0, abs=0.1)


def test_protein_matches_icmr_at_the_reference_woman_weight():
    assert targets_for(WOMAN)["protein"].rda == pytest.approx(45.7, abs=0.1)


def test_protein_scales_with_actual_weight():
    heavier = Body(sex="male", age=25, weight_kg=90.0, activity="sedentary")

    assert targets_for(heavier)["protein"].rda == pytest.approx(74.7, abs=0.1)


"""
ICMR footnotes that a cereal-based diet with low-quality protein needs
1 g/kg/day rather than 0.83. A rice-dominant diet without adequate pulses and
milk is exactly that case.
"""


def test_a_cereal_dominant_diet_raises_protein_to_one_gram_per_kilo():
    assert targets_for(MAN, cereal_dominant=True)["protein"].rda == pytest.approx(65.0, abs=0.1)


def test_the_protein_floor_uses_the_ear_coefficient():
    assert targets_for(MAN)["protein"].ear == pytest.approx(0.66 * 65, abs=0.1)


# ICMR sets fibre at 30 g per 2,000 kcal, so it moves with the energy target.
def test_fibre_scales_with_the_energy_target():
    targets = targets_for(MAN)
    energy = targets["energy"].rda

    assert targets["fibre"].rda == pytest.approx(energy / 2000 * 30, abs=0.1)


def test_a_larger_energy_target_means_more_fibre():
    sedentary = targets_for(Body(sex="male", age=25, weight_kg=65, activity="sedentary"))
    heavy = targets_for(Body(sex="male", age=25, weight_kg=65, activity="heavy"))

    assert heavy["fibre"].rda > sedentary["fibre"].rda


# New in ICMR-NIN 2020, and the reason a very low energy target still needs carbs.
def test_carbohydrate_never_falls_below_the_daily_floor():
    tiny = Body(sex="female", age=70, weight_kg=40, activity="sedentary")

    assert targets_for(tiny)["carbohydrate"].rda >= 130


def test_micronutrients_come_straight_from_the_reference_table():
    targets = targets_for(MAN)

    assert targets["calcium"].rda == 1000
    assert targets["calcium"].ear == 800


# ICMR publishes an AI rather than an RDA for some nutrients.
def test_a_nutrient_published_as_an_adequate_intake_uses_that_figure():
    assert targets_for(MAN)["sodium"].rda == 2000


"""
Sodium's figure is a ceiling inclusive of invisible salt, not something to reach.
Treating it as a target would make a low-sodium day look like a failure.
"""


def test_sodium_is_a_ceiling_rather_than_a_target():
    assert targets_for(MAN)["sodium"].kind == "ceiling"


def test_calcium_is_a_target_rather_than_a_ceiling():
    assert targets_for(MAN)["calcium"].kind == "target"


def test_upper_limits_are_attached_where_icmr_defines_one():
    assert targets_for(MAN)["calcium"].tul == 2500


# ICMR deliberately set no limit for B12 — inventing one would be a bug.
def test_a_nutrient_with_no_published_limit_carries_none():
    assert targets_for(MAN)["vitamin_b12"].tul is None


def test_energy_is_included_as_a_target():
    assert targets_for(MAN)["energy"].rda == pytest.approx(2110, abs=12)


def test_a_reference_row_that_is_absent_produces_no_target():
    """The seed covers 60 rows, not every nutrient in every band. A missing row
    must be left out rather than defaulted to zero, which would read as a
    shortfall on every single day."""
    targets = build_targets(
        MAN,
        goal="maintain",
        pace=None,
        cereal_dominant=False,
        references={"calcium": ReferenceValue(ear=800, rda=1000, ai=None)},
        upper_limits={},
    )

    assert "iron" not in targets


"""
A weight-driven recalibration moves the energy target, and with it everything
ICMR derives from energy: the macros, fibre, and the four B vitamins stored per
activity level. It must not move protein, which is per kilogram of the weight
the body actually has, nor the RDA-anchored micronutrients.
"""


def recalibrated(offset: float, body: Body = MAN):
    return build_targets(
        body,
        goal="maintain",
        pace=None,
        cereal_dominant=False,
        references=REFERENCES,
        upper_limits=UPPER_LIMITS,
        energy_offset_kcal=offset,
    )


def test_without_an_offset_every_target_is_exactly_what_it_was():
    assert recalibrated(0.0) == targets_for(MAN)


def test_an_offset_moves_the_energy_target():
    formula = targets_for(MAN)["energy"].rda
    assert recalibrated(-200.0)["energy"].rda == pytest.approx(formula - 200.0)


def test_the_macros_and_fibre_follow_the_recalibrated_energy():
    moved = recalibrated(-200.0)
    energy = moved["energy"].rda

    assert moved["fibre"].rda == pytest.approx(energy / 2000.0 * 30.0)
    assert moved["fat"].rda == pytest.approx(energy * 0.25 / 9.0)
    assert moved["saturated_fat"].rda == pytest.approx(energy * 0.10 / 9.0)


def test_the_energy_scaled_b_vitamins_follow_it_by_the_same_ratio():
    base, moved = targets_for(MAN), recalibrated(-200.0)
    ratio = moved["energy"].rda / base["energy"].rda

    assert moved["thiamine"].rda == pytest.approx(1.4 * ratio)
    assert moved["thiamine"].ear == pytest.approx(1.2 * ratio)


def test_protein_and_the_rda_anchored_micronutrients_do_not_move():
    base, moved = targets_for(MAN), recalibrated(-200.0)

    assert moved["protein"] == base["protein"]
    assert moved["calcium"] == base["calcium"]
    assert moved["iron"] == base["iron"]
    assert moved["vitamin_b12"] == base["vitamin_b12"]


def test_an_offset_beyond_the_bound_is_held_to_ten_percent():
    formula = targets_for(MAN)["energy"].rda
    assert recalibrated(-900.0)["energy"].rda == pytest.approx(formula * 0.9)


def test_a_reference_row_carries_its_source():
    assert ReferenceValue(ear=5, rda=8, ai=None, source="IOM").source == "IOM"
    assert ReferenceValue(ear=5, rda=8, ai=None).source is None
