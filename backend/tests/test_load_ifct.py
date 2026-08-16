from pathlib import Path

import pytest

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_ifct import load_ifct
from etl.load_nutrients import seed_nutrients

FIXTURE = Path(__file__).parent / "fixtures" / "ifct_sample.csv"


def _value(db, ingredient_code, nutrient_code):
    return (
        db.query(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Ingredient.code == ingredient_code, Nutrient.code == nutrient_code)
        .one()
        .per_100g
    )


def test_loads_every_row(db):
    seed_nutrients(db)

    count = load_ifct(db, FIXTURE)

    assert count == 3
    assert db.query(Ingredient).filter_by(source="IFCT").count() == 3


def test_energy_is_converted_from_kilojoules_to_kcal(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # 449 kJ / 4.184 = 107.3 kcal — buffalo milk is about 100 kcal/100 ml.
    assert _value(db, "ifct:D005", "energy") == pytest.approx(107.3, abs=0.5)


def test_calcium_is_converted_from_grams_to_milligrams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # The single most dangerous conversion: 0.121 g must become 121 mg,
    # not 0.121 mg. Getting this wrong understates calcium 1000-fold.
    assert _value(db, "ifct:D005", "calcium") == pytest.approx(121.0, abs=0.1)


def test_trace_nutrients_are_converted_from_grams_to_micrograms(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # Egg vitamin A: 0.000156 g = 156 ug.
    assert _value(db, "ifct:E001", "vitamin_a") == pytest.approx(156.0, abs=1.0)


def test_proximates_stay_in_grams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    assert _value(db, "ifct:E001", "protein") == pytest.approx(13.28, abs=0.01)


def test_diet_tags_and_aliases_are_kept(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    egg = db.query(Ingredient).filter_by(code="ifct:E001").one()
    amaranth = db.query(Ingredient).filter_by(code="ifct:A001").one()

    assert "eggetarian" in egg.diet_tags
    assert "vegetarian" not in egg.diet_tags
    assert "Keerai" in amaranth.search_aliases


def test_b12_and_iodine_are_absent_from_ifct(db):
    """IFCT publishes neither; they must come from USDA in Task 4."""
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    for code in ("vitamin_b12", "iodine"):
        assert (
            db.query(IngredientNutrient)
            .join(Nutrient)
            .filter(Nutrient.code == code)
            .count()
            == 0
        )


def test_loading_twice_does_not_duplicate(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)
    load_ifct(db, FIXTURE)

    assert db.query(Ingredient).filter_by(code="ifct:A001").count() == 1
