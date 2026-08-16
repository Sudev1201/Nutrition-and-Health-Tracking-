import pytest

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from etl.load_nutrients import seed_nutrients
from etl.load_reference import seed_reference


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
