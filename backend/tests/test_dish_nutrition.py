import pytest

from app.foods.nutrition import (
    compute_dish_nutrients,
    compute_dish_nutrients_bulk,
    nutrients_for_portion,
)
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


# --- the bulk path the planner reads through ----------------------------------------------


def test_the_bulk_loader_agrees_with_the_single_dish_figure(db, simple_dish):
    """`load_pool` reads every dish through the bulk path, so the formula must not fork.

    Rice carries two nutrients here so its weight appears on two joined rows; the
    dedupe that counts it once is the part a one-nutrient recipe would never test.
    """
    calcium = db.query(Nutrient).filter_by(code="calcium").one()
    rice = db.query(Ingredient).filter_by(code="t:rice").one()
    db.add(IngredientNutrient(ingredient_id=rice.id, nutrient_id=calcium.id, per_100g=10.0))
    db.flush()

    single = compute_dish_nutrients(db, simple_dish)
    bulk = compute_dish_nutrients_bulk(db, [simple_dish.id])

    assert bulk == {simple_dish.id: single}
    # 10 mg in 200 g raw, 400 g cooked: 2.5 mg per 100 g as served. Had rice's
    # weight been counted twice, this would read 2.0 and protein 6.0.
    assert bulk[simple_dish.id]["calcium"] == pytest.approx(2.5)
    assert bulk[simple_dish.id]["protein"] == pytest.approx(7.5)


def test_the_bulk_loader_leaves_out_a_dish_with_no_recipe(db, simple_dish):
    """Absent rather than empty: the caller falls back to the fixed per-100g values."""
    fixed = Dish(code="t:fixed", name="Fixed", source="indb", is_editable=False)
    db.add(fixed)
    db.flush()

    bulk = compute_dish_nutrients_bulk(db, [simple_dish.id, fixed.id])

    assert set(bulk) == {simple_dish.id}
    assert compute_dish_nutrients_bulk(db, []) == {}
