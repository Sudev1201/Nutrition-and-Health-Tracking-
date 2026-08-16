import pytest

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients
from etl.load_usda import load_usda_gapfill


@pytest.fixture
def usda_files(tmp_path):
    (tmp_path / "food.csv").write_text(
        "fdc_id,data_type,description\n"
        "1001,foundation_food,\"Milk, whole\"\n"
        "1002,foundation_food,\"Egg, whole, raw\"\n"
    )
    (tmp_path / "nutrient.csv").write_text(
        "id,name,unit_name\n"
        "1178,Vitamin B-12,UG\n"
        '1100,"Iodine, I",UG\n'
    )
    (tmp_path / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount\n"
        "1,1001,1178,0.45\n"
        "2,1002,1178,0.89\n"
    )
    return tmp_path


def test_attaches_b12_to_matching_ingredients(db, usda_files):
    seed_nutrients(db)
    milk = Ingredient(code="ifct:D005", name="Milk, whole, Buffalo", source="IFCT")
    db.add(milk)
    db.flush()

    load_usda_gapfill(
        db,
        usda_files / "food.csv",
        usda_files / "nutrient.csv",
        usda_files / "food_nutrient.csv",
    )

    value = (
        db.query(IngredientNutrient)
        .join(Nutrient)
        .filter(
            IngredientNutrient.ingredient_id == milk.id, Nutrient.code == "vitamin_b12"
        )
        .one()
    )
    assert value.per_100g == pytest.approx(0.45)
    assert value.source == "USDA"


def test_ifct_values_are_never_overwritten(db, usda_files):
    """USDA fills gaps; where IFCT has a value it wins, since it is the
    Indian composition authority for Indian foods."""
    seed_nutrients(db)
    milk = Ingredient(code="ifct:D005", name="Milk, whole, Buffalo", source="IFCT")
    db.add(milk)
    db.flush()
    b12 = db.query(Nutrient).filter_by(code="vitamin_b12").one()
    db.add(
        IngredientNutrient(
            ingredient_id=milk.id, nutrient_id=b12.id, per_100g=0.36, source="IFCT"
        )
    )
    db.flush()

    load_usda_gapfill(
        db,
        usda_files / "food.csv",
        usda_files / "nutrient.csv",
        usda_files / "food_nutrient.csv",
    )

    stored = db.query(IngredientNutrient).filter_by(ingredient_id=milk.id).one()
    assert stored.per_100g == pytest.approx(0.36)
    assert stored.source == "IFCT"
