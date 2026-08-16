from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Dish, DishIngredient, DishNutrient, IngredientNutrient
from app.models.nutrient import Nutrient


def compute_dish_nutrients(db: Session, dish: Dish) -> dict[str, float]:
    """Nutrients per 100 g of the dish as served.

    Authored dishes are summed from their recipe and divided by the cooked
    weight, so `yield_factor` matters: rice absorbs water and dilutes per-gram
    values, a dosa loses water and concentrates them. Imported dishes carry
    fixed per-100g values instead, since they have no recipe.
    """
    rows = list(
        db.execute(
            select(DishIngredient, IngredientNutrient, Nutrient)
            .join(
                IngredientNutrient,
                IngredientNutrient.ingredient_id == DishIngredient.ingredient_id,
            )
            .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
            .where(DishIngredient.dish_id == dish.id)
        )
    )

    if not rows:
        fixed = list(
            db.execute(
                select(DishNutrient, Nutrient)
                .join(Nutrient, Nutrient.id == DishNutrient.nutrient_id)
                .where(DishNutrient.dish_id == dish.id)
            )
        )
        return {nutrient.code: value.per_100g for value, nutrient in fixed}

    totals: dict[str, float] = {}
    raw_grams = 0.0
    seen_ingredients: set = set()

    for dish_ingredient, ingredient_nutrient, nutrient in rows:
        if dish_ingredient.id not in seen_ingredients:
            raw_grams += dish_ingredient.grams
            seen_ingredients.add(dish_ingredient.id)
        contribution = ingredient_nutrient.per_100g * dish_ingredient.grams / 100.0
        totals[nutrient.code] = totals.get(nutrient.code, 0.0) + contribution

    cooked_grams = raw_grams * (dish.yield_factor or 1.0)
    if cooked_grams <= 0:
        return {}

    return {code: total * 100.0 / cooked_grams for code, total in totals.items()}


def nutrients_for_portion(db: Session, dish: Dish, grams: float) -> dict[str, float]:
    per_100g = compute_dish_nutrients(db, dish)
    return {code: value * grams / 100.0 for code, value in per_100g.items()}
