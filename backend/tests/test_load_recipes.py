import pytest
from sqlalchemy import func

from app.models.food import Dish, DishIngredient, Ingredient, PortionMeasure
from etl.load_nutrients import seed_nutrients
from etl.load_recipes import RecipeIngredientMissing, load_recipes
from etl.recipes.south_indian import RECIPES, Recipe


@pytest.fixture
def rice_and_dal(db):
    seed_nutrients(db)
    for code, name in [("ifct:B001", "Bengal gram, dal"), ("ifct:A015", "Rice, raw, milled")]:
        db.add(Ingredient(code=code, name=name, source="IFCT"))
    db.flush()


def test_loads_a_recipe_with_its_ingredients(db, rice_and_dal):
    """Builds its own recipe from the fixture ingredients rather than filtering
    RECIPES down to them.

    The brief's original version filtered the seed set for a recipe using ONLY
    two fixture codes; no real dish is two ingredients of rice and channa dal,
    so it skipped every run and asserted nothing. Constructing the recipe here
    means the loader's three write paths -- the dish row, its ingredient rows
    and its portion measures -- are all actually checked.
    """
    recipe = Recipe(
        code="si:test_kootu",
        name="Test kootu",
        slot_tags="lunch dinner",
        diet_tags="vegetarian",
        yield_factor=1.6,
        serves=4,
        measures=[("1 cup", 195.0), ("1 ladle", 100.0)],
        ingredients=[("ifct:A015", 250.0), ("ifct:B001", 100.0)],
    )

    assert load_recipes(db, [recipe]) == 1

    dish = db.query(Dish).filter_by(code="si:test_kootu").one()
    assert dish.name == "Test kootu"
    assert dish.source == "authored"
    assert dish.is_editable is True
    assert dish.slot_tags == "lunch dinner"
    assert dish.diet_tags == "vegetarian"
    assert dish.yield_factor == pytest.approx(1.6)

    ingredients_by_code = {
        i.code: grams
        for i, grams in db.query(Ingredient, DishIngredient.grams)
        .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
        .filter(DishIngredient.dish_id == dish.id)
        .all()
    }
    assert ingredients_by_code == {"ifct:A015": 250.0, "ifct:B001": 100.0}

    measures = (
        db.query(PortionMeasure)
        .filter_by(dish_id=dish.id)
        .order_by(PortionMeasure.grams.desc())
        .all()
    )
    assert [(m.measure_name, m.grams, m.is_default) for m in measures] == [
        ("1 cup", 195.0, True),
        ("1 ladle", 100.0, False),
    ]


def test_reloading_a_recipe_does_not_duplicate_its_rows(db, rice_and_dal):
    recipe = Recipe(
        code="si:test_kootu",
        name="Test kootu",
        slot_tags="lunch",
        diet_tags="vegetarian",
        yield_factor=1.6,
        serves=4,
        measures=[("1 cup", 195.0)],
        ingredients=[("ifct:A015", 250.0)],
    )

    load_recipes(db, [recipe])
    load_recipes(db, [recipe])

    dish = db.query(Dish).filter_by(code="si:test_kootu").one()
    assert db.query(DishIngredient).filter_by(dish_id=dish.id).count() == 1
    assert db.query(PortionMeasure).filter_by(dish_id=dish.id).count() == 1


def test_a_missing_ingredient_is_a_loud_failure(db, rice_and_dal):
    bogus = Recipe(
        code="si:bogus",
        name="Bogus",
        slot_tags="lunch",
        diet_tags="vegetarian",
        yield_factor=1.0,
        serves=1,
        measures=[("serving", 100.0)],
        ingredients=[("ifct:DOES-NOT-EXIST", 50.0)],
    )

    with pytest.raises(RecipeIngredientMissing):
        load_recipes(db, [bogus])


def test_every_seed_recipe_references_real_ingredients(db):
    """Guards the whole seed set against typos in ingredient codes."""
    seed_nutrients(db)
    from etl.common import cached_download
    from etl.load_ifct import IFCT_URL, load_ifct
    from etl.load_manual_ingredients import seed_manual_ingredients

    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))
    seed_manual_ingredients(db)
    known = {i.code for i in db.query(Ingredient).all()}

    missing = {
        code
        for recipe in RECIPES
        for code, _ in recipe.ingredients
        if code not in known
    }

    assert missing == set()


def test_the_seed_set_covers_the_staples(db):
    names = {r.name.lower() for r in RECIPES}
    for staple in ["idli", "sambar", "rasam", "curd rice", "filter coffee"]:
        assert any(staple in n for n in names), f"missing {staple}"


def test_recipe_codes_are_unique(db):
    codes = [r.code for r in RECIPES]

    assert len(codes) == len(set(codes))


def test_the_fish_dishes_are_a_variant_set_the_user_can_choose_from(db):
    """Fish is not hardcoded to one species: the planner has to be able to offer
    the fish the user actually bought, and IFCT's marine fish differ by more
    than a factor of ten in fat (anchovy 0.78 g vs sardine 8.99 g per 100 g)."""
    kuzhambu = [r for r in RECIPES if r.code.startswith("si:fish_kuzhambu_")]
    fry = [r for r in RECIPES if r.code.startswith("si:fish_fry_")]

    assert len(kuzhambu) >= 3
    assert len(fry) >= 3

    for group in (kuzhambu, fry):
        # A shared display prefix is what makes them group in a picker.
        assert len({r.name.split("(")[0].strip() for r in group}) == 1
        # Only the fish differs; every other ingredient row is identical.
        non_fish = {
            tuple(sorted((c, g) for c, g in r.ingredients if not c.startswith("ifct:P")))
            for r in group
        }
        assert len(non_fish) == 1
        fish_codes = {c for r in group for c, _ in r.ingredients if c.startswith("ifct:P")}
        assert len(fish_codes) == len(group)


def test_coffee_and_tea_are_built_from_brewed_liquid_not_dry_grounds(db):
    """Listing 24 g of coffee powder credits the cup with the full composition
    of grounds that are steeped and thrown away. The drinks must reference the
    brewed-liquid ingredients instead."""
    drinks = [
        r
        for r in RECIPES
        if r.code in {"si:filter_coffee_sugar", "si:filter_coffee_plain", "si:tea",
                      "si:tea_no_sugar"}
    ]

    assert len(drinks) == 4
    for recipe in drinks:
        codes = {code for code, _ in recipe.ingredients}
        assert codes & {"usda:coffee_brewed", "usda:tea_brewed"}, recipe.code
        assert "manual:coffee_powder" not in codes
        assert "manual:tea_leaves" not in codes
        # Already-liquid ingredients: nothing is absorbed or boiled off.
        assert recipe.yield_factor == pytest.approx(1.0), recipe.code


def test_the_batter_dishes_use_the_four_to_one_ratio(db):
    """The household ratio is 4:1 rice to urad dal by volume, i.e. 400 g rice to
    95 g dal by weight -- not the 3:1 (400:125) first drafted. Idli and dosa are
    eaten daily, so a 30% overstatement of the dal would inflate protein in
    every breakfast the app ever logs."""
    for code, rice_code in [
        ("si:idli", "ifct:A014"),
        ("si:dosa_plain", "ifct:A014"),
        ("si:dosa_masala", "ifct:A014"),
        ("si:uttapam", "ifct:A014"),
    ]:
        recipe = next(r for r in RECIPES if r.code == code)
        grams = dict(recipe.ingredients)
        assert grams[rice_code] / grams["ifct:B003"] == pytest.approx(400 / 95, rel=0.02), code


def test_every_recipe_is_internally_consistent(db):
    """Cheap arithmetic guards that catch a copy-paste slip in 72 hand-written
    recipes: a measure bigger than the whole batch, a batch that cannot feed the
    servings it claims, or a duplicated ingredient row."""
    for recipe in RECIPES:
        assert recipe.serves >= 1, recipe.code
        assert recipe.measures, recipe.code
        assert recipe.ingredients, recipe.code

        codes = [code for code, _ in recipe.ingredients]
        assert len(codes) == len(set(codes)), f"{recipe.code} repeats an ingredient"
        assert all(grams > 0 for _, grams in recipe.ingredients), recipe.code

        cooked = sum(grams for _, grams in recipe.ingredients) * recipe.yield_factor
        # 2% slack: household measures are rounded to whole grams, so a
        # single-serving dish's measure can round just past its own batch.
        assert max(grams for _, grams in recipe.measures) <= cooked * 1.02, (
            f"{recipe.code}: a portion measure is larger than the whole batch"
        )
        # The default measure times `serves` should be the batch, give or take
        # the rounding a household measure invites.
        assert recipe.measures[0][1] * recipe.serves == pytest.approx(cooked, rel=0.12), (
            f"{recipe.code}: {recipe.serves} x {recipe.measures[0][1]} g does not "
            f"account for a {cooked:.0f} g batch"
        )


def test_no_dish_is_saltier_than_home_cooking(db):
    """THE SALT INVARIANT. Salt as a fraction of FINISHED weight, not raw.

    The bug this catches is mechanical, not a matter of taste: salt gets set per
    raw batch and then a sub-1.0 yield factor concentrates it, so a 110 g
    vegetable side ends up out-salting a full cup of sambar. Every dish that
    breached this had that same cause.

    1.2% NaCl of finished weight is the ceiling for food meant to be eaten as a
    dish. Sambar sits at 0.66%, which is at or below normal palatability, and
    the modelled day totals ~9.9 g of salt -- squarely inside measured Indian
    intake of 8-11 g/day. So this is a ceiling on outliers, not a diet.

    Powders and podis are exempt: a spice blend genuinely is that salty, and it
    is eaten by the teaspoon, not the bowl.
    """
    exempt = {r.code for r in RECIPES if r.code.endswith("_powder") or "podi" in r.code}

    too_salty = {}
    for recipe in RECIPES:
        if recipe.code in exempt:
            continue
        salt = sum(grams for code, grams in recipe.ingredients if code == "manual:salt")
        if not salt:
            continue
        cooked = sum(grams for _, grams in recipe.ingredients) * recipe.yield_factor
        fraction = salt / cooked
        if fraction > 0.012:
            too_salty[recipe.code] = f"{fraction:.2%} ({salt} g in {cooked:.0f} g)"

    assert too_salty == {}


def test_the_default_portion_is_the_smaller_reviewed_one_for_chutneys(db):
    """measures[0] becomes is_default, and the reviewed document bolds 2 tbsp.

    Called out separately because ordering is invisible at a glance: nothing
    about `measures=[("1 serving", 80.0), ("2 tbsp", 40.0)]` looks wrong, yet it
    silently doubles what every chutney tap logs.
    """
    for code, expected in [
        ("si:chutney_coconut", ("2 tbsp", 40.0)),
        ("si:chutney_tomato", ("2 tbsp", 40.0)),
        ("si:chutney_coriander", ("2 tbsp", 35.0)),
        ("si:chutney_mint", ("2 tbsp", 35.0)),
    ]:
        recipe = next(r for r in RECIPES if r.code == code)
        assert recipe.measures[0] == expected, code


def test_the_default_measure_is_written_as_the_only_default(db, rice_and_dal):
    """Ordering only matters if the loader honours it. Pin that too."""
    recipe = Recipe(
        code="si:test_chutney",
        name="Test chutney",
        slot_tags="lunch",
        diet_tags="vegetarian",
        yield_factor=1.0,
        serves=2,
        measures=[("2 tbsp", 40.0), ("1 serving", 80.0)],
        ingredients=[("ifct:A015", 80.0)],
    )

    load_recipes(db, [recipe])

    dish = db.query(Dish).filter_by(code="si:test_chutney").one()
    defaults = db.query(PortionMeasure).filter_by(dish_id=dish.id, is_default=True).all()
    assert [(m.measure_name, m.grams) for m in defaults] == [("2 tbsp", 40.0)]


def test_the_two_pongals_agree_about_ghee(db):
    """They are the same dish class eaten at the same meal; a 50% difference in
    ghee per serving between them is an inconsistency, not a recipe."""
    per_serving = {}
    for code in ("si:ven_pongal", "si:sakkarai_pongal"):
        recipe = next(r for r in RECIPES if r.code == code)
        ghee = sum(grams for c, grams in recipe.ingredients if c == "ifct:T013")
        per_serving[code] = ghee / recipe.serves

    assert per_serving["si:ven_pongal"] == pytest.approx(6.0)
    assert per_serving["si:sakkarai_pongal"] == pytest.approx(7.5)


def test_loading_the_whole_seed_set(db):
    seed_nutrients(db)
    from etl.common import cached_download
    from etl.load_ifct import IFCT_URL, load_ifct
    from etl.load_manual_ingredients import seed_manual_ingredients

    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))
    seed_manual_ingredients(db)

    assert load_recipes(db, RECIPES) == len(RECIPES)
    assert db.query(Dish).count() == len(RECIPES)
    assert db.query(DishIngredient).count() == sum(len(r.ingredients) for r in RECIPES)
    assert db.query(PortionMeasure).count() == sum(len(r.measures) for r in RECIPES)


def test_reloading_the_whole_seed_set_lands_on_the_exact_expected_totals(db):
    """Loads the full 72-dish set twice in ONE session and pins the exact
    expected DishIngredient/PortionMeasure totals both times -- not merely
    "unchanged between the two loads", which a bug that stabilises on a wrong
    number (e.g. orphaned rows a delete failed to clear) could still pass.
    Asserting against `sum(len(r.ingredients) for r in RECIPES)` /
    `sum(len(r.measures) for r in RECIPES)` catches that shape of bug too.
    """
    seed_nutrients(db)
    from etl.common import cached_download
    from etl.load_ifct import IFCT_URL, load_ifct
    from etl.load_manual_ingredients import seed_manual_ingredients

    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))
    seed_manual_ingredients(db)

    expected_ingredients = sum(len(r.ingredients) for r in RECIPES)
    expected_measures = sum(len(r.measures) for r in RECIPES)
    expected_per_dish = {r.code: len(r.ingredients) for r in RECIPES}

    def per_dish_ingredient_counts():
        return dict(
            db.query(Dish.code, func.count(DishIngredient.id))
            .join(DishIngredient, DishIngredient.dish_id == Dish.id)
            .group_by(Dish.code)
            .all()
        )

    for pass_number in (1, 2):
        load_recipes(db, RECIPES)
        assert db.query(DishIngredient).count() == expected_ingredients, pass_number
        assert db.query(PortionMeasure).count() == expected_measures, pass_number
        # Totals alone would still pass if one dish kept an orphan row and
        # another lost one, so pin the shape as well as the sum.
        assert per_dish_ingredient_counts() == expected_per_dish, pass_number
