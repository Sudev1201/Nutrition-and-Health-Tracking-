import pytest
from sqlalchemy import select

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_manual_ingredients import MANUAL_INGREDIENTS, seed_manual_ingredients
from etl.load_nutrients import seed_nutrients


def _per_100g(db, ingredient_code: str, nutrient_code: str) -> float | None:
    row = db.scalar(
        select(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(Ingredient.code == ingredient_code, Nutrient.code == nutrient_code)
    )
    return None if row is None else row.per_100g


@pytest.fixture
def seeded(db):
    seed_nutrients(db)
    seed_manual_ingredients(db)
    return db


def test_salt_sodium_is_the_real_thing(seeded):
    """The single most load-bearing number in the recipe set.

    40 of the 66 authored dishes contain salt, and sodium drives the whole
    hypertension rule set. USDA fdc 746775 "Salt, table, iodized" says 38,700
    mg/100 g, which is 98.4% of pure NaCl's 39,337 mg -- the balance being the
    water, anticaking agent and iodate a real retail salt contains.
    """
    sodium = _per_100g(seeded, "manual:salt", "sodium")

    assert sodium == pytest.approx(38700.0, abs=100.0)


def test_salt_iodine_is_the_indian_fortification_level_not_the_american_one(seeded):
    """USDA's own row says 5,080 ug/100 g -- the US ~50 ppm level. India
    mandates 15 ppm at retail (FSSAI Fortification of Foods Regulations 2018),
    so copying USDA would overstate iodine by 3.4x."""
    iodine = _per_100g(seeded, "manual:salt", "iodine")

    assert iodine == pytest.approx(1500.0)


def test_salt_carries_no_energy_and_no_vitamins(seeded):
    for code in ["energy", "protein", "fat", "carbohydrate", "vitamin_c", "vitamin_b12"]:
        assert _per_100g(seeded, "manual:salt", code) == 0.0, code


def test_curd_comes_from_usda_with_a_usable_b12(seeded):
    ingredient = seeded.scalar(select(Ingredient).where(Ingredient.code == "usda:curd"))

    assert ingredient.source == "USDA"
    assert _per_100g(seeded, "usda:curd", "protein") == pytest.approx(3.824)
    assert _per_100g(seeded, "usda:curd", "calcium") == pytest.approx(126.8)
    # Curd is a daily B12 source for a lacto-vegetarian; a NULL here would
    # silently zero the B12 story for five dishes.
    assert _per_100g(seeded, "usda:curd", "vitamin_b12") == pytest.approx(0.37)


def test_curd_iodine_is_deliberately_absent(seeded):
    """US dairy iodine is iodophor sanitiser residue from US milking practice,
    not a property of milk -- the same reason etl.load_usda's CURATED_ANIMAL_MAP
    pairs cow milk for B12 only. Unknown must read as unknown."""
    assert _per_100g(seeded, "usda:curd", "iodine") is None


def test_curd_lactose_is_not_counted_as_free_sugar(seeded):
    """Total sugars are 4.09 g, all of it milk's own lactose and galactose.
    Free sugars exclude lactose naturally present in milk products."""
    assert _per_100g(seeded, "usda:curd", "carbohydrate") == pytest.approx(5.575)
    assert _per_100g(seeded, "usda:curd", "free_sugar") == 0.0


def test_sugar_is_pure_carbohydrate_and_all_of_it_is_free(seeded):
    assert _per_100g(seeded, "manual:sugar", "carbohydrate") == pytest.approx(99.98)
    assert _per_100g(seeded, "manual:sugar", "free_sugar") == pytest.approx(99.8)
    assert _per_100g(seeded, "manual:sugar", "energy") == pytest.approx(387.0)
    assert _per_100g(seeded, "manual:sugar", "protein") == 0.0


def test_brewed_drinks_are_priced_per_100g_of_liquid(seeded):
    """A cup of coffee is 99% water. If these looked like ground coffee or dry
    tea leaves -- hundreds of kcal per 100 g -- the recipes would be crediting
    the drinker with grounds that were steeped and thrown away."""
    for code in ["usda:coffee_brewed", "usda:tea_brewed"]:
        assert _per_100g(seeded, code, "energy") == pytest.approx(1.0), code
        assert _per_100g(seeded, code, "fat") < 0.1, code
        assert _per_100g(seeded, code, "free_sugar") == 0.0, code

    # Tea is a real manganese source; coffee is a real potassium one. Both only
    # show up on a liquid basis.
    assert _per_100g(seeded, "usda:tea_brewed", "manganese") == pytest.approx(0.219)
    assert _per_100g(seeded, "usda:coffee_brewed", "potassium") == pytest.approx(49.0)


def test_every_manual_ingredient_carries_the_macros_a_recipe_needs(seeded):
    """A recipe that hits a NULL macro produces a silently wrong dish total."""
    required = ["energy", "protein", "fat", "carbohydrate", "fibre", "sodium"]

    for spec in MANUAL_INGREDIENTS:
        for nutrient_code in required:
            assert _per_100g(seeded, spec.code, nutrient_code) is not None, (
                f"{spec.code} has no {nutrient_code}"
            )


def test_the_nutrient_rows_record_which_source_each_number_came_from(seeded):
    """Salt and curd are mixed-provenance, so provenance has to be per nutrient
    rather than per ingredient."""
    sodium = seeded.scalar(
        select(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(Ingredient.code == "manual:salt", Nutrient.code == "sodium")
    )
    iodine = seeded.scalar(
        select(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(Ingredient.code == "manual:salt", Nutrient.code == "iodine")
    )
    b12 = seeded.scalar(
        select(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .where(Ingredient.code == "usda:curd", Nutrient.code == "vitamin_b12")
    )

    assert sodium.source == "USDA"
    assert iodine.source == "FSSAI-2018"
    assert b12.source == "USDA:SR-legacy"


def test_seeding_twice_changes_nothing(db):
    seed_nutrients(db)
    first = seed_manual_ingredients(db)
    ingredients_after_first = db.query(Ingredient).count()
    rows_after_first = db.query(IngredientNutrient).count()

    second = seed_manual_ingredients(db)

    assert (first, second) == (len(MANUAL_INGREDIENTS), len(MANUAL_INGREDIENTS))
    assert db.query(Ingredient).count() == ingredients_after_first
    assert db.query(IngredientNutrient).count() == rows_after_first
    assert _per_100g(db, "manual:salt", "sodium") == pytest.approx(38700.0)
