import pytest

from app.foods.nutrition import compute_dish_nutrients, nutrients_for_portion
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients


@pytest.fixture
def simple_dish(db):
    seed_nutrients(db)
    protein = db.query(Nutrient).filter_by(code="protein").one()

    rice = Ingredient(code="t:rice", name="Rice", source="IFCT")
    dal = Ingredient(code="t:dal", name="Dal", source="IFCT")
    db.add_all([rice, dal])
    db.flush()
    # 7 g protein per 100 g rice, 23 g per 100 g dal.
    db.add(IngredientNutrient(ingredient_id=rice.id, nutrient_id=protein.id, per_100g=7.0))
    db.add(IngredientNutrient(ingredient_id=dal.id, nutrient_id=protein.id, per_100g=23.0))

    dish = Dish(code="t:dish", name="Test dish", source="authored", is_editable=True,
                yield_factor=2.0)
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=rice.id, grams=100.0))
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=dal.id, grams=100.0))
    db.flush()
    return dish


def test_totals_are_expressed_per_100g_as_served(db, simple_dish):
    # 7 g + 23 g = 30 g protein in 200 g raw, which yields 400 g cooked,
    # so 7.5 g per 100 g as served.
    values = compute_dish_nutrients(db, simple_dish)

    assert values["protein"] == pytest.approx(7.5)


def test_a_portion_scales_from_the_per_100g_figure(db, simple_dish):
    values = nutrients_for_portion(db, simple_dish, grams=200.0)

    assert values["protein"] == pytest.approx(15.0)


def test_an_empty_recipe_yields_nothing_rather_than_failing(db):
    seed_nutrients(db)
    dish = Dish(code="t:empty", name="Empty", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    assert compute_dish_nutrients(db, dish) == {}
