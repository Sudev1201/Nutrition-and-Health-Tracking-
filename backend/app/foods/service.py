from itertools import zip_longest

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.food import Dish, Ingredient


class EmptySearchQuery(ValueError):
    """A search term with nothing in it but whitespace.

    Stripped, it becomes "", the LIKE pattern becomes "%%", and every dish in
    the database matches -- so a stray space used to return twenty arbitrary
    dishes presented as search results. Refused here rather than at the router
    alone, so plan 5's diary and any other caller get the same answer.
    """


def search_foods(db: Session, query: str, limit: int = 20) -> list[dict]:
    """Search dishes and ingredients by name or regional alias.

    Both kinds are always reachable. The previous version ran the dish query
    first, capped at `limit`, then appended ingredients and truncated the
    concatenation back to `limit` -- so once `limit` dishes matched, no
    ingredient could ever be returned. "rice" matched 30 dishes and 7
    ingredients and returned 0 ingredients, which left `ifct:A015 Rice, raw,
    milled` -- an ingredient nearly every recipe uses -- unreachable through
    the only search endpoint there is.

    Interleaving one of each fixes it without a fixed quota: whichever side has
    fewer matches yields its slots to the other, so a query that matches only
    dishes still fills the page with dishes.

    `Ingredient.search_aliases` is nullable. In SQL, `NULL ILIKE pattern`
    evaluates to NULL, not false -- but that only matters if it's the only
    predicate. Here it sits in an `or_()` alongside `Ingredient.name.ilike`,
    and three-valued logic makes `TRUE OR NULL = TRUE` / `FALSE OR NULL = NULL`
    (excluded, same as `FALSE`): an ingredient with no aliases is still found
    whenever its name matches, and is correctly excluded when neither does.
    """
    term = query.strip()
    if not term:
        raise EmptySearchQuery("a search query needs at least one non-whitespace character")

    pattern = f"%{term}%"

    dishes = db.scalars(select(Dish).where(Dish.name.ilike(pattern)).limit(limit)).all()
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

    results: list[dict] = []
    for dish, ingredient in zip_longest(dishes, ingredients):
        if dish is not None:
            results.append(
                {
                    "id": str(dish.id),
                    "kind": "dish",
                    "name": dish.name,
                    "source": dish.source,
                    "is_editable": dish.is_editable,
                }
            )
        if ingredient is not None:
            results.append(
                {
                    "id": str(ingredient.id),
                    "kind": "ingredient",
                    "name": ingredient.name,
                    "source": ingredient.source,
                    "is_editable": False,
                }
            )
    return results[:limit]
