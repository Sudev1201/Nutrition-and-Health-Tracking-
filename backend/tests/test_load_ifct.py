from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.common import ColumnMapUnresolved, cached_download
from etl.load_ifct import (
    ATWATER_MIN_KCAL,
    ATWATER_SOURCE,
    IFCT_COLUMN_MAP,
    IFCT_URL,
    INTRINSIC_SUGAR_SOURCE,
    OXALATE_CLASS,
    load_ifct,
)
from etl.load_nutrients import seed_nutrients

FIXTURE = Path(__file__).parent / "fixtures" / "ifct_sample.csv"


def _row(db, ingredient_code, nutrient_code):
    return (
        db.query(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Ingredient.code == ingredient_code, Nutrient.code == nutrient_code)
        .one()
    )


def _value(db, ingredient_code, nutrient_code):
    return _row(db, ingredient_code, nutrient_code).per_100g


def _source(db, ingredient_code, nutrient_code):
    return _row(db, ingredient_code, nutrient_code).source


def test_loads_every_row(db):
    seed_nutrients(db)

    count = load_ifct(db, FIXTURE)

    assert count == 6
    assert db.query(Ingredient).filter_by(source="IFCT").count() == 6


def test_energy_is_converted_from_kilojoules_to_kcal(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # 449 kJ / 4.184 = 107.3 kcal — buffalo milk is about 100 kcal/100 ml.
    assert _value(db, "ifct:D005", "energy") == pytest.approx(107.3, abs=0.5)


def test_calcium_is_converted_from_grams_to_milligrams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # The single most dangerous conversion: 0.121 g must become 121 mg,
    # not 0.121 mg. Getting this wrong understates calcium 1000-fold.
    assert _value(db, "ifct:D005", "calcium") == pytest.approx(121.0, abs=0.1)


def test_trace_nutrients_are_converted_from_grams_to_micrograms(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # Egg vitamin A: 0.000156 g = 156 ug.
    assert _value(db, "ifct:E001", "vitamin_a") == pytest.approx(156.0, abs=1.0)


def test_proximates_stay_in_grams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    assert _value(db, "ifct:E001", "protein") == pytest.approx(13.28, abs=0.01)


def test_diet_tags_and_aliases_are_kept(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    egg = db.query(Ingredient).filter_by(code="ifct:E001").one()
    amaranth = db.query(Ingredient).filter_by(code="ifct:A001").one()

    assert "eggetarian" in egg.diet_tags
    assert "vegetarian" not in egg.diet_tags
    assert "Keerai" in amaranth.search_aliases


def test_b12_and_iodine_are_absent_from_ifct(db):
    """IFCT publishes neither; they must come from USDA in Task 4."""
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    for code in ("vitamin_b12", "iodine"):
        assert (
            db.query(IngredientNutrient)
            .join(Nutrient)
            .filter(Nutrient.code == code)
            .count()
            == 0
        )


def test_a_sugars_group_food_takes_its_free_sugar_from_ifct(db):
    """Jaggery IS free sugar: the whole 84.32 g counts."""
    seed_nutrients(db)

    load_ifct(db, FIXTURE)

    assert _value(db, "ifct:I001", "free_sugar") == pytest.approx(84.32)
    assert _source(db, "ifct:I001", "free_sugar") == "IFCT"


def test_intrinsic_sugars_are_an_explicit_zero_not_the_total_sugar_figure(db):
    """IFCT's `fsugar` is TOTAL sugars. Milk's lactose and an apple's fructose
    are intrinsic, so free sugar is 0 -- asserted, with a tag saying why, not
    copied from a column that would overstate every fruit and dairy food."""
    seed_nutrients(db)

    load_ifct(db, FIXTURE)

    for code in ("ifct:D005", "ifct:E001", "ifct:A001"):
        assert _value(db, code, "free_sugar") == 0.0, code
        assert _source(db, code, "free_sugar") == INTRINSIC_SUGAR_SOURCE, code


def test_free_sugar_zero_is_written_for_every_food_in_the_real_dataset(db):
    """The defect this closes: free_sugar had no IFCT mapping at all, so 542
    foods carried no row and every authored dish's free sugar was either
    missing or a hard zero it had not earned. Every food must now carry a
    figure, and only the Sugars group and the one juice row may be non-zero.
    """
    seed_nutrients(db)
    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))

    rows = (
        db.query(Ingredient.code, Ingredient.food_group, IngredientNutrient.per_100g)
        .join(IngredientNutrient, IngredientNutrient.ingredient_id == Ingredient.id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Nutrient.code == "free_sugar")
        .all()
    )

    assert len(rows) == db.query(Ingredient).filter_by(source="IFCT").count()
    non_zero = {code: group for code, group, value in rows if value > 0}
    assert non_zero == {
        "ifct:I001": "Sugars",  # Jaggery, cane
        "ifct:I002": "Sugars",  # Sugarcane, juice
        "ifct:E033": "Fruits",  # Lemon, juice -- a pressed juice is free sugar
    }


def test_the_spec_named_greens_carry_an_oxalate_class(db):
    """Spec design doc 437-441: "all keerai is calcium" is wrong. Palak and
    arai keerai are high-oxalate, murungai keerai and curry leaf are not."""
    seed_nutrients(db)
    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))

    classes = dict(
        db.query(Ingredient.code, Ingredient.oxalate_class)
        .filter(Ingredient.oxalate_class.isnot(None))
        .all()
    )

    assert classes == {f"ifct:{code}": value for code, value in OXALATE_CLASS.items()}
    assert classes["ifct:C033"] == "high"  # Spinach (palak)
    assert classes["ifct:C002"] == "high"  # Amaranth leaves, green (arai keerai)
    assert classes["ifct:C019"] == "low"  # Drumstick leaves (murungai keerai)
    assert classes["ifct:G010"] == "low"  # Curry leaves


def test_a_column_map_typo_is_a_loud_failure(db, tmp_path):
    """The mechanism that hid the missing free-sugar mapping for a whole plan:
    an unresolved column was skipped silently, one nutrient at a time, across
    every row. load_recipes already raises on the analogous condition."""
    seed_nutrients(db)

    with (
        pytest.raises(ColumnMapUnresolved, match="unseeded nutrient codes"),
        patch.dict(IFCT_COLUMN_MAP, {"ca": ("calcuim", "g")}),
    ):
        load_ifct(db, FIXTURE)

    with (
        pytest.raises(ColumnMapUnresolved, match="columns absent from the source"),
        patch.dict(IFCT_COLUMN_MAP, {"calcium_mg": ("calcium", "g")}),
    ):
        load_ifct(db, FIXTURE)


def test_loading_twice_does_not_duplicate(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)
    load_ifct(db, FIXTURE)

    assert db.query(Ingredient).filter_by(code="ifct:A001").count() == 1


def test_a_published_zero_energy_is_derived_from_the_food_s_own_macros(db):
    """IFCT publishes enerc=0 for pure fat. Taking that literally zeroes the
    calories of the most energy-dense thing in the pantry."""
    seed_nutrients(db)

    load_ifct(db, FIXTURE)

    # Fixture row ifct:T004 Gingelly oil: enerc=0, fatce=100 -> 900 kcal.
    assert _value(db, "ifct:T004", "energy") == pytest.approx(900.0, abs=1.0)
    assert _source(db, "ifct:T004", "energy") == ATWATER_SOURCE
    # A real published figure is never overridden.
    assert _source(db, "ifct:D005", "energy") == "IFCT"


def test_a_genuine_zero_stays_zero(db):
    """Not every zero is a defect. Only a zero its own macro row contradicts."""
    seed_nutrients(db)

    load_ifct(db, FIXTURE)

    # Fixture row ifct:W001: enerc=0 with no meaningful macros -- water.
    assert _value(db, "ifct:W001", "energy") == 0.0
    assert _source(db, "ifct:W001", "energy") == "IFCT"


def test_reloading_corrects_a_stale_energy_row_and_its_provenance(db):
    """The database already holds every oil at 0 kcal tagged "IFCT". A re-run
    has to fix the value AND the source, not just the value."""
    seed_nutrients(db)
    load_ifct(db, FIXTURE)
    row = (
        db.query(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Ingredient.code == "ifct:T004", Nutrient.code == "energy")
        .one()
    )
    row.per_100g, row.source = 0.0, "IFCT"  # simulate the already-loaded defect
    db.flush()

    load_ifct(db, FIXTURE)

    assert _value(db, "ifct:T004", "energy") == pytest.approx(900.0, abs=1.0)
    assert _source(db, "ifct:T004", "energy") == ATWATER_SOURCE


def test_no_ingredient_in_the_real_dataset_has_impossible_zero_energy(db):
    """THE GUARD. Against the real 542-row IFCT dataset, no food may report zero
    energy while its own protein, fat and carbohydrate imply otherwise.

    This is the check that would have caught the oils-at-0-kcal defect before it
    reached 40+ dishes, and it is deliberately expressed as an arithmetic
    invariant over every row rather than a spot-check of the 14 known ones -- a
    future IFCT release could add a fifteenth.
    """
    seed_nutrients(db)
    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))

    per_100g: dict[str, dict[str, float]] = defaultdict(dict)
    rows = (
        db.query(Ingredient.code, Nutrient.code, IngredientNutrient.per_100g)
        .join(IngredientNutrient, IngredientNutrient.ingredient_id == Ingredient.id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Nutrient.code.in_(["energy", "protein", "fat", "carbohydrate"]))
        .all()
    )
    for ingredient_code, nutrient_code, value in rows:
        per_100g[ingredient_code][nutrient_code] = value

    impossible = {
        code: values
        for code, values in per_100g.items()
        if values.get("energy", 0.0) <= 0.0
        and (
            4 * values.get("protein", 0.0)
            + 4 * values.get("carbohydrate", 0.0)
            + 9 * values.get("fat", 0.0)
        )
        > ATWATER_MIN_KCAL
    }

    assert impossible == {}


def test_the_oils_all_carry_real_energy_after_the_real_load(db):
    """The 14 rows that were wrong. 100 g of fat is ~900 kcal by definition."""
    seed_nutrients(db)
    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))

    oils = (
        db.query(Ingredient.code, IngredientNutrient.per_100g, IngredientNutrient.source)
        .join(IngredientNutrient, IngredientNutrient.ingredient_id == Ingredient.id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Ingredient.food_group == "Edible Oils and Fats", Nutrient.code == "energy")
        .all()
    )

    assert len(oils) == 14
    for code, value, source in oils:
        assert value == pytest.approx(900.0, abs=5.0), code
        assert source == ATWATER_SOURCE, code
