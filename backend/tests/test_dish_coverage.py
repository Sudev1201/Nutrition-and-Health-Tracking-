"""Dish-level coverage invariants.

`app.foods.nutrition.compute_dish_nutrients` sums ingredient values. A nutrient
with no row on an ingredient contributes nothing to that sum, and the sum is
still reported as if it were complete -- so "unknown must read as unknown",
which holds at the ingredient layer, is erased at the dish layer. Both defects
this file pins had exactly that shape: a number absent from the source arriving
downstream as a confident zero.

These are deliberately expressed over the whole authored set rather than as
spot-checks of the dishes that were wrong, because the next gap will be in a
different dish.
"""

import pytest
from sqlalchemy import text

from app.foods.nutrition import compute_dish_nutrients, dish_coverage
from app.models.food import Dish, DishIngredient, Ingredient
from etl.common import cached_download
from etl.load_ifct import IFCT_URL, load_ifct
from etl.load_manual_ingredients import seed_manual_ingredients
from etl.load_nutrients import seed_nutrients
from etl.load_recipes import load_recipes
from etl.load_usda import load_usda_gapfill
from etl.recipes.south_indian import RECIPES
from etl.run_all import _usda_csv_paths

ANIMAL_GROUPS = frozenset(
    {
        "Marine Fish",
        "Animal Meat",
        "Poultry",
        "Egg and Egg Products",
        "Fresh Water Fish and Shellfish",
        "Marine Shellfish",
        "Marine Mollusks",
        "Milk and Milk Products",
    }
)
SUGAR_GROUPS = frozenset({"Sugars"})


@pytest.fixture
def seeded(db):
    """The real pipeline, in run_all's order, minus the INDB reference dishes
    (which carry their own per-100g values and no recipe)."""
    seed_nutrients(db)
    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))
    seed_manual_ingredients(db)
    load_usda_gapfill(db, *_usda_csv_paths())
    load_recipes(db, RECIPES)

    # Purely a test-harness concern. These 16,747 ingredient_nutrients rows
    # live in a transaction that has not committed, so Postgres has no
    # statistics for them and plans the dish-nutrient join as though the table
    # were empty: 28 s per dish instead of 0.09 s. ANALYZE is safe inside a
    # transaction block (VACUUM is not). The real database is committed and
    # autovacuumed, and is fast without this.
    db.execute(text("analyze"))
    return db


def _groups_by_dish(db) -> dict[Dish, set[str]]:
    rows = (
        db.query(Dish, Ingredient.food_group)
        .join(DishIngredient, DishIngredient.dish_id == Dish.id)
        .join(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
        .filter(Dish.source == "authored")
        .all()
    )
    grouped: dict[Dish, set[str]] = {}
    for dish, food_group in rows:
        grouped.setdefault(dish, set()).add(food_group)
    return grouped


def test_a_dish_with_a_sugars_ingredient_never_reports_zero_free_sugar(seeded):
    """IFCT publishes total sugars in `fsugar` but the loader mapped no column
    to free_sugar at all, so sakkarai pongal (150 g of jaggery) reported free
    sugar ABSENT, and sundal and carrot poriyal reported a confident 0.0 --
    against a nutrient that is a tracked, excess-sensitive cap.
    """
    offenders = {}
    for dish, groups in _groups_by_dish(seeded).items():
        if not groups & SUGAR_GROUPS:
            continue
        value = compute_dish_nutrients(seeded, dish).get("free_sugar")
        if not value:
            offenders[dish.code] = value

    assert offenders == {}


def test_a_dish_with_an_animal_ingredient_never_reports_zero_b12(seeded):
    """Every plant ingredient carries an explicit derived:plant-b12-zero, so a
    fish with no B12 row does not make the dish read "unknown" -- it makes it
    read 0.0, confidently, for the nutrient that drives the whole
    vegetarian-observance compensation rule.
    """
    offenders = {}
    for dish, groups in _groups_by_dish(seeded).items():
        if not groups & ANIMAL_GROUPS:
            continue
        value = compute_dish_nutrients(seeded, dish).get("vitamin_b12")
        if not value:
            offenders[dish.code] = value

    assert offenders == {}


def test_a_fish_dish_out_scores_a_cup_of_coffee_for_b12(seeded):
    """The symptom that made the defect visible: with the fish contributing
    nothing, filter coffee -- whose B12 is the milk in it -- out-scored every
    fish dish on the menu.

    Chicken curry is deliberately not in this comparison. Its 0.19 ug/100 g
    against coffee's 0.34 is not a defect: a cup of coffee is mostly milk,
    while 100 g of curry is mostly gravy, and per-100-g is the basis. It is
    covered by the zero-invariant above, which is the claim that matters.
    """
    dishes = {dish.code: dish for dish in seeded.query(Dish).filter_by(source="authored")}

    coffee = compute_dish_nutrients(seeded, dishes["si:filter_coffee_sugar"])["vitamin_b12"]
    for code in ("si:fish_kuzhambu_sardine", "si:fish_fry_vanjaram"):
        assert compute_dish_nutrients(seeded, dishes[code])["vitamin_b12"] > coffee, code


# --- iodine: the gap that cannot be closed by filling it ---------------------
#
# Unlike free sugar and B12, iodine has no defensible zero-fill. IFCT publishes
# none, INDB publishes none, and USDA's dairy and egg figures reflect US iodophor
# sanitiser and feed-fortification practice rather than the food itself -- which
# is why `load_usda` refuses them and `manual:salt` takes its figure from FSSAI.
#
# So "never reports zero iodine" is not a satisfiable invariant here. The
# invariant that *is* satisfiable, and the one that matters, is that a dish must
# not present a partial iodine figure as though it were complete.


def test_a_dish_reports_how_much_of_its_iodine_figure_is_measured(seeded):
    """Every authored dish is either honest about iodine or has no iodine number.

    A figure with no coverage alongside it is the defect: iodine reaches the
    database on exactly one ingredient that any recipe uses -- iodised salt -- so
    a dish that reports iodine is reporting salt, and the rest of its weight is
    unmeasured.
    """
    offenders = {}
    for dish in _groups_by_dish(seeded):
        amount = compute_dish_nutrients(seeded, dish).get("iodine")
        if amount is None:
            continue
        coverage = dish_coverage(seeded, dish).get("iodine", 0.0)
        if coverage <= 0.0 or coverage > 1.0:
            offenders[dish.code] = coverage

    assert offenders == {}


def test_a_salted_dish_does_not_claim_its_whole_weight_was_measured_for_iodine(seeded):
    """Salt is a few grams in a few hundred, so coverage must read as the small
    fraction it is. If this ever reports 1.0, iodine has been zero-filled onto
    ingredients nobody measured."""
    dishes = {dish.code: dish for dish in _groups_by_dish(seeded)}
    salted = [
        code
        for code, dish in dishes.items()
        if compute_dish_nutrients(seeded, dish).get("iodine")
    ]
    assert salted, "expected at least one dish to carry iodine from iodised salt"

    overclaiming = {
        code: dish_coverage(seeded, dishes[code]).get("iodine", 0.0)
        for code in salted
        if dish_coverage(seeded, dishes[code]).get("iodine", 0.0) >= 1.0
    }
    assert overclaiming == {}
