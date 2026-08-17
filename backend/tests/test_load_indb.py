from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest

from app.models.food import Dish, DishNutrient, PortionMeasure
from app.models.nutrient import Nutrient
from etl.common import ColumnMapUnresolved
from etl.load_indb import INDB_COLUMN_MAP, load_indb
from etl.load_nutrients import seed_nutrients

# Mirrors the real workbook's layout: food_code, food_name, primarysource,
# the per-100g nutrient columns, servings_unit, then unit_serving_energy_kcal
# -- the one unit_serving_* column the loader actually reads.
HEADER = [
    "food_code",
    "food_name",
    "primarysource",
    *INDB_COLUMN_MAP.keys(),
    "servings_unit",
    "unit_serving_energy_kcal",
]


@pytest.fixture
def indb_workbook(tmp_path) -> Path:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(HEADER)

    def row(food_code, food_name, energy_kcal, calcium_mg, servings_unit, unit_serving_energy_kcal):
        values = {
            "food_code": food_code,
            "food_name": food_name,
            "primarysource": "test",
            "energy_kcal": energy_kcal,
            "calcium_mg": calcium_mg,
            "servings_unit": servings_unit,
            "unit_serving_energy_kcal": unit_serving_energy_kcal,
        }
        sheet.append([values.get(column) for column in HEADER])

    # A normal dish: 150 kcal/100g, 120 mg calcium/100g, and one "tea cup"
    # serving worth 300 kcal -- so a tea cup should weigh 200 g.
    row("A001", "Test Sambar", 150.0, 120.0, "tea cup", 300.0)
    # Water: a genuine zero-calorie row. Must not crash the import or derive
    # an absurd portion weight from a zero/zero energy ratio.
    row("W001", "Test Water", 0.0, 0.0, "tall glass", 0.0)

    path = tmp_path / "indb_sample.xlsx"
    workbook.save(path)
    return path


def test_dish_is_created_as_a_non_editable_indb_reference(db, indb_workbook):
    seed_nutrients(db)

    load_indb(db, indb_workbook)

    dish = db.query(Dish).filter_by(code="indb:A001").one()
    assert dish.source == "INDB"
    assert dish.is_editable is False
    assert dish.name == "Test Sambar"


def test_calcium_lands_in_milligrams(db, indb_workbook):
    seed_nutrients(db)
    calcium = db.query(Nutrient).filter_by(code="calcium").one()
    assert calcium.unit == "mg"

    load_indb(db, indb_workbook)

    dish = db.query(Dish).filter_by(code="indb:A001").one()
    value = db.query(DishNutrient).filter_by(dish_id=dish.id, nutrient_id=calcium.id).one()
    assert value.per_100g == pytest.approx(120.0)


def test_a_portion_measure_is_derived_from_the_serving_energy(db, indb_workbook):
    seed_nutrients(db)

    load_indb(db, indb_workbook)

    dish = db.query(Dish).filter_by(code="indb:A001").one()
    measure = db.query(PortionMeasure).filter_by(dish_id=dish.id).one()
    assert measure.measure_name == "tea cup"
    # 300 kcal in a tea cup at 150 kcal/100g == 200 g.
    assert measure.grams == pytest.approx(200.0)
    assert measure.is_default is True


def test_a_zero_calorie_row_does_not_crash_or_produce_a_portion(db, indb_workbook):
    seed_nutrients(db)

    loaded = load_indb(db, indb_workbook)

    assert loaded == 2
    dish = db.query(Dish).filter_by(code="indb:W001").one()
    assert db.query(PortionMeasure).filter_by(dish_id=dish.id).count() == 0


def test_free_sugar_is_imported_for_reference_dishes(db, indb_workbook):
    """INDB publishes free sugar directly, and it is a tracked cap."""
    assert INDB_COLUMN_MAP["freesugar_g"] == ("free_sugar", "g")


def test_a_column_map_typo_is_a_loud_failure(db, indb_workbook):
    """A single unresolved entry used to be skipped silently for all 1,014
    rows -- the same mechanism that hid the missing IFCT free-sugar mapping."""
    seed_nutrients(db)

    with (
        pytest.raises(ColumnMapUnresolved, match="unseeded nutrient codes"),
        patch.dict(INDB_COLUMN_MAP, {"calcium_mg": ("calcuim", "mg")}),
    ):
        load_indb(db, indb_workbook)

    with (
        pytest.raises(ColumnMapUnresolved, match="columns absent from the source"),
        patch.dict(INDB_COLUMN_MAP, {"ca": ("calcium", "mg")}),
    ):
        load_indb(db, indb_workbook)


def test_reloading_does_not_duplicate(db, indb_workbook):
    seed_nutrients(db)

    load_indb(db, indb_workbook)
    load_indb(db, indb_workbook)

    assert db.query(Dish).filter_by(code="indb:A001").count() == 1
    dish = db.query(Dish).filter_by(code="indb:A001").one()
    assert db.query(DishNutrient).filter_by(dish_id=dish.id).count() == 2
    assert db.query(PortionMeasure).filter_by(dish_id=dish.id).count() == 1
