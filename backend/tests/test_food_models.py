import pytest
from sqlalchemy.exc import IntegrityError

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient


def _ingredient(db, code="ifct:A001", name="Amaranth seed"):
    ing = Ingredient(code=code, name=name, source="IFCT", food_group="Cereals")
    db.add(ing)
    db.flush()
    return ing


def test_ingredient_codes_are_unique(db):
    _ingredient(db)
    db.add(Ingredient(code="ifct:A001", name="Duplicate", source="IFCT"))

    with pytest.raises(IntegrityError):
        db.flush()


def test_nutrient_values_attach_to_an_ingredient(db):
    ing = _ingredient(db)
    calcium = Nutrient(
        code="calcium", display_name="Calcium", unit="mg", category="mineral"
    )
    db.add(calcium)
    db.flush()

    db.add(IngredientNutrient(ingredient_id=ing.id, nutrient_id=calcium.id, per_100g=181.0))
    db.flush()

    stored = db.query(IngredientNutrient).one()
    assert stored.per_100g == 181.0


def test_a_seed_dish_has_no_creator(db):
    dish = Dish(code="si:idli", name="Idli", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    assert dish.created_by_user_id is None
    assert dish.yield_factor == 1.0


def test_a_recipe_links_ingredients_with_gram_amounts(db):
    ing = _ingredient(db)
    dish = Dish(code="si:idli", name="Idli", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ing.id, grams=60.0))
    db.flush()

    assert db.query(DishIngredient).one().grams == 60.0
