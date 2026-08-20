from sqlalchemy import func, select
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


def dish_coverage(db: Session, dish: Dish) -> dict[str, float]:
    """Per nutrient code, the share of the dish's ingredient weight that carried a
    value for it.

    `compute_dish_nutrients` inner-joins, so an ingredient with no row for a
    nutrient contributes nothing to the numerator while its weight still counts
    in the denominator. The resulting figure is understated but indistinguishable
    from a complete one -- "unknown must read as unknown" holds at the ingredient
    layer and was being erased at the dish layer. This is the missing half: how
    much of the dish the number actually speaks for.

    A code absent from the result is 0%-covered, which avoids having to enumerate
    the whole nutrient table to say so.
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
        # An imported dish carries fixed per-100g values and has no recipe to
        # measure against, so whatever it publishes covers all of it -- and
        # whatever it omits covers none.
        fixed = db.execute(
            select(Nutrient.code)
            .join(DishNutrient, DishNutrient.nutrient_id == Nutrient.id)
            .where(DishNutrient.dish_id == dish.id)
        ).scalars()
        return {code: 1.0 for code in fixed}

    total_grams = 0.0
    seen_ingredients: set = set()
    covered_grams: dict[str, float] = {}

    for dish_ingredient, _value, nutrient in rows:
        if dish_ingredient.id not in seen_ingredients:
            total_grams += dish_ingredient.grams
            seen_ingredients.add(dish_ingredient.id)
        covered_grams[nutrient.code] = (
            covered_grams.get(nutrient.code, 0.0) + dish_ingredient.grams
        )

    # Ingredients with no nutrient rows at all never appear in the join, so the
    # denominator has to come from the recipe rather than from `rows`.
    recipe_grams = db.execute(
        select(func.coalesce(func.sum(DishIngredient.grams), 0.0)).where(
            DishIngredient.dish_id == dish.id
        )
    ).scalar_one()
    total_grams = float(recipe_grams) or total_grams

    if total_grams <= 0:
        return {}

    return {code: min(grams / total_grams, 1.0) for code, grams in covered_grams.items()}


def nutrients_for_portion(db: Session, dish: Dish, grams: float) -> dict[str, float]:
    per_100g = compute_dish_nutrients(db, dish)
    return {code: value * grams / 100.0 for code, value in per_100g.items()}
