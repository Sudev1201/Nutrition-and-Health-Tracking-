import pytest

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from etl.load_nutrients import seed_nutrients
from etl.load_reference import RDA_ROWS, seed_reference


def _rda(db, nutrient_code, sex, activity=None, age_band="18-59"):
    return (
        db.query(RdaReference)
        .join(Nutrient)
        .filter(
            Nutrient.code == nutrient_code,
            RdaReference.sex == sex,
            RdaReference.age_band == age_band,
            RdaReference.activity_level == activity,
        )
        .one()
    )


def test_calcium_matches_the_published_icmr_figure(db):
    seed_nutrients(db)
    seed_reference(db)

    calcium = _rda(db, "calcium", "male")

    assert calcium.rda == pytest.approx(1000)
    assert calcium.ear == pytest.approx(800)
    assert calcium.source == "ICMR-NIN-2020"


def test_womens_iron_is_higher_than_mens(db):
    """29 vs 19 mg — the female figure already averages menstrual loss across
    the cycle, which is why the cycle feature must not raise it further."""
    seed_nutrients(db)
    seed_reference(db)

    assert _rda(db, "iron", "female").rda == pytest.approx(29)
    assert _rda(db, "iron", "male").rda == pytest.approx(19)


def test_b_vitamins_are_indexed_by_activity(db):
    seed_nutrients(db)
    seed_reference(db)

    sedentary = _rda(db, "thiamine", "male", activity="sedentary")
    moderate = _rda(db, "thiamine", "male", activity="moderate")

    assert sedentary.rda == pytest.approx(1.4)
    assert moderate.rda == pytest.approx(1.8)
    assert sedentary.rda < moderate.rda


@pytest.mark.parametrize(
    "nutrient_code,sex",
    [
        ("thiamine", "male"),
        ("thiamine", "female"),
        ("riboflavin", "male"),
        ("riboflavin", "female"),
        ("niacin", "male"),
        ("niacin", "female"),
        ("vitamin_b6", "male"),
        ("vitamin_b6", "female"),
    ],
)
def test_sedentary_is_always_below_moderate_below_heavy(db, nutrient_code, sex):
    """Regression for a data bug where female vitamin_b6 sedentary (1.9) was
    seeded identical to its own moderate value — this must hold for all four
    energy-scaled B vitamins and both sexes, not just one nutrient/sex pair."""
    seed_nutrients(db)
    seed_reference(db)

    sedentary = _rda(db, nutrient_code, sex, activity="sedentary")
    moderate = _rda(db, nutrient_code, sex, activity="moderate")
    heavy = _rda(db, nutrient_code, sex, activity="heavy")

    assert sedentary.rda < moderate.rda < heavy.rda


def test_ear_never_exceeds_rda():
    """RDA is defined as EAR plus roughly two standard deviations, so RDA > EAR
    must hold wherever a row gives both — an EAR at or above its own RDA would
    hand the compensation engine a floor above its own target. Universal
    property of the DRI framework, so checked across the whole table rather
    than per nutrient (this is what let round 1's flat-copied B-vitamin EARs
    slip through: EAR >= RDA on several sedentary rows)."""
    for code, sex, age_band, activity, ear, rda, ai, source in RDA_ROWS:
        if ear is not None and rda is not None:
            assert ear < rda, (
                f"{code}/{sex}/{age_band}/{activity}: EAR {ear} >= RDA {rda} ({source})"
            )


def test_elderly_calcium_and_vitamin_d_rise(db):
    seed_nutrients(db)
    seed_reference(db)

    assert _rda(db, "calcium", "male", age_band="60+").rda == pytest.approx(1200)
    # 20 ug = 800 IU, up from 15 ug = 600 IU for the general adult band.
    assert _rda(db, "vitamin_d", "male", age_band="60+").rda == pytest.approx(20)


def test_magnesium_upper_limit_is_supplemental_only(db):
    seed_nutrients(db)
    seed_reference(db)

    magnesium = (
        db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == "magnesium").one()
    )

    assert magnesium.value == pytest.approx(350)
    assert magnesium.supplemental_only is True


def test_nutrients_icmr_left_open_have_no_upper_limit(db):
    """ICMR deliberately set none for these — the app must not invent one."""
    seed_nutrients(db)
    seed_reference(db)

    for code in ("thiamine", "riboflavin", "biotin", "vitamin_b12", "potassium"):
        assert (
            db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == code).count() == 0
        )


def test_iron_upper_limit_is_the_indian_value(db):
    seed_nutrients(db)
    seed_reference(db)

    iron = db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == "iron").one()

    assert iron.value == pytest.approx(45)
    assert iron.source == "ICMR-2018-TUL"
