"""Write authored recipes into dishes, dish_ingredients and portion_measures.

Nutrients are never copied here. A dish's numbers are computed from its
ingredient rows, so correcting one IFCT ingredient corrects every dish that
uses it -- which is the whole reason recipes reference codes rather than
carrying their own per-100g values.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Dish, DishIngredient, Ingredient, PortionMeasure


class RecipeIngredientMissing(Exception):
    """A recipe references an ingredient code that is not in the database.

    Deliberately fatal rather than skipped: a dropped ingredient produces a
    dish that still loads, still looks complete, and is silently short of
    whatever that ingredient contributed. A typo in a code has to stop the
    build, not quietly shrink a meal.
    """


def load_recipes(db: Session, recipes: Iterable) -> int:
    """Insert or update the given recipes. Safe to re-run.

    Ingredient and measure rows are replaced wholesale on each run rather than
    merged, so removing an ingredient from a recipe actually removes it from
    the dish instead of leaving an orphan behind.
    """
    ingredients = {i.code: i for i in db.scalars(select(Ingredient))}
    loaded = 0

    for recipe in recipes:
        missing = [code for code, _ in recipe.ingredients if code not in ingredients]
        if missing:
            raise RecipeIngredientMissing(f"{recipe.code} references unknown {missing}")

        dish = db.scalar(select(Dish).where(Dish.code == recipe.code))
        if dish is None:
            dish = Dish(code=recipe.code, source="authored", is_editable=True)
            db.add(dish)
        dish.name = recipe.name
        dish.slot_tags = recipe.slot_tags
        dish.diet_tags = recipe.diet_tags
        dish.yield_factor = recipe.yield_factor
        db.flush()

        # Flush immediately after each bulk delete, before the replacement rows
        # are added. `SessionLocal` is built with autoflush=False, so without
        # this the inserts sit pending while later iterations issue their own
        # DELETEs, and the statement order across the 72-dish loop stops being
        # something this function pins down. `synchronize_session=False` keeps
        # the delete from scanning the whole identity map, which in the
        # orchestrator's single long-lived session is tens of thousands of rows.
        db.query(DishIngredient).filter_by(dish_id=dish.id).delete(
            synchronize_session=False
        )
        db.flush()
        for code, grams in recipe.ingredients:
            db.add(
                DishIngredient(
                    dish_id=dish.id, ingredient_id=ingredients[code].id, grams=grams
                )
            )

        db.query(PortionMeasure).filter_by(dish_id=dish.id).delete(
            synchronize_session=False
        )
        db.flush()
        for index, (measure_name, grams) in enumerate(recipe.measures):
            db.add(
                PortionMeasure(
                    dish_id=dish.id,
                    measure_name=measure_name,
                    grams=grams,
                    # The first measure listed is the one the app pre-selects,
                    # so recipes order theirs most-likely-tap first.
                    is_default=(index == 0),
                )
            )

        # And once more before moving on, so a dish's rows are fully written
        # before the next dish's DELETEs run rather than trailing an iteration
        # behind them.
        db.flush()
        loaded += 1

    db.flush()
    return loaded
