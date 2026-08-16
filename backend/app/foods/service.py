from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.food import Dish, Ingredient


def search_foods(db: Session, query: str, limit: int = 20) -> list[dict]:
    """Search dishes and ingredients by name or regional alias.

    `Ingredient.search_aliases` is nullable. In SQL, `NULL ILIKE pattern`
    evaluates to NULL, not false -- but that only matters if it's the only
    predicate. Here it sits in an `or_()` alongside `Ingredient.name.ilike`,
    and three-valued logic makes `TRUE OR NULL = TRUE` / `FALSE OR NULL = NULL`
    (excluded, same as `FALSE`): an ingredient with no aliases is still found
    whenever its name matches, and is correctly excluded when neither does.
    """
    pattern = f"%{query.strip()}%"

    dishes = db.scalars(
        select(Dish).where(Dish.name.ilike(pattern)).limit(limit)
    ).all()
    ingredients = db.scalars(
        select(Ingredient)
        .where(
            or_(
                Ingredient.name.ilike(pattern),
                Ingredient.search_aliases.ilike(pattern),
            )
        )
        .limit(limit)
    ).all()

    results = [
        {
            "id": str(d.id),
            "kind": "dish",
            "name": d.name,
            "source": d.source,
            "is_editable": d.is_editable,
        }
        for d in dishes
    ] + [
        {
            "id": str(i.id),
            "kind": "ingredient",
            "name": i.name,
            "source": i.source,
            "is_editable": False,
        }
        for i in ingredients
    ]
    return results[:limit]
