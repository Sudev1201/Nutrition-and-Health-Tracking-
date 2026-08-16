import pytest

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients
from etl.load_usda import load_usda_gapfill


@pytest.fixture
def usda_files(tmp_path):
    """Small CSV fixtures mirroring FoodData Central's real layout, keyed to
    three of the real entries in etl.load_usda.CURATED_ANIMAL_MAP: cow milk
    (fdc 322892, B12-only pairing), whole egg (fdc 748967, B12-only pairing),
    and tilapia (fdc 2684442, B12+iodine pairing).

    The USDA source data itself DOES carry an iodine amount for milk and egg
    (37.9 and 49.1 ug/100g) -- deliberately, so the "no iodine row" tests
    prove the exclusion comes from CURATED_ANIMAL_MAP's per-nutrient opt-in,
    not merely from the fixture lacking the data.
    """
    (tmp_path / "food.csv").write_text(
        "fdc_id,data_type,description\n"
        "322892,foundation_food,\"Milk, whole, 3.25% milkfat, with added vitamin D\"\n"
        "748967,foundation_food,\"Eggs, Grade A, Large, egg whole\"\n"
        "2684442,foundation_food,\"Fish, tilapia, farm raised, raw\"\n"
    )
    (tmp_path / "nutrient.csv").write_text(
        "id,name,unit_name\n"
        "1178,Vitamin B-12,UG\n"
        '1100,"Iodine, I",UG\n'
    )
    (tmp_path / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount\n"
        "1,322892,1178,0.54\n"
        "2,322892,1100,37.9\n"
        "3,748967,1178,1.02\n"
        "4,748967,1100,49.1\n"
        "5,2684442,1178,0.7594\n"
        "6,2684442,1100,4.145\n"
    )
    return tmp_path


def _run(db, usda_files):
    return load_usda_gapfill(
        db,
        usda_files / "food.csv",
        usda_files / "nutrient.csv",
        usda_files / "food_nutrient.csv",
    )


def _value(db, ingredient_id, code):
    return (
        db.query(IngredientNutrient)
        .join(Nutrient)
        .filter(IngredientNutrient.ingredient_id == ingredient_id, Nutrient.code == code)
        .one_or_none()
    )


def test_plant_group_ingredient_gets_explicit_b12_zero(db, usda_files):
    seed_nutrients(db)
    banana = Ingredient(code="ifct:J001", name="Banana", source="IFCT", food_group="Fruits")
    db.add(banana)
    db.flush()

    _run(db, usda_files)

    value = _value(db, banana.id, "vitamin_b12")
    assert value is not None
    assert value.per_100g == pytest.approx(0.0)
    assert value.source == "derived:plant-b12-zero"


def test_uncurated_animal_ingredient_has_no_b12_row(db, usda_files):
    """An animal-group ingredient with no entry in CURATED_ANIMAL_MAP stays
    null -- it is unknown, not zero."""
    seed_nutrients(db)
    goat = Ingredient(code="ifct:N999", name="Goat, meat, raw", source="IFCT", food_group="Animal Meat")
    db.add(goat)
    db.flush()

    _run(db, usda_files)

    assert _value(db, goat.id, "vitamin_b12") is None


def test_curated_ingredient_gets_b12_from_usda(db, usda_files):
    seed_nutrients(db)
    egg = Ingredient(
        code="ifct:M001",
        name="Egg, poultry, whole, raw",
        source="IFCT",
        food_group="Egg and Egg Products",
    )
    db.add(egg)
    db.flush()

    _run(db, usda_files)

    value = _value(db, egg.id, "vitamin_b12")
    assert value is not None
    assert value.per_100g == pytest.approx(1.02)
    assert value.source == "USDA"


def test_existing_ifct_value_is_never_overwritten(db, usda_files):
    """USDA fills gaps; where IFCT has a value it wins, since it is the
    Indian composition authority for Indian foods."""
    seed_nutrients(db)
    milk = Ingredient(
        code="ifct:L002",
        name="Milk, whole, Cow",
        source="IFCT",
        food_group="Milk and Milk Products",
    )
    db.add(milk)
    db.flush()
    b12 = db.query(Nutrient).filter_by(code="vitamin_b12").one()
    db.add(IngredientNutrient(ingredient_id=milk.id, nutrient_id=b12.id, per_100g=0.36, source="IFCT"))
    db.flush()

    _run(db, usda_files)

    stored = _value(db, milk.id, "vitamin_b12")
    assert stored.per_100g == pytest.approx(0.36)
    assert stored.source == "IFCT"


def test_plant_group_ingredient_gets_no_iodine_row(db, usda_files):
    """Plant iodine is soil-dependent, not reliably zero, so it is never
    zero-filled -- only the curated animal map ever attaches iodine."""
    seed_nutrients(db)
    banana = Ingredient(code="ifct:J001", name="Banana", source="IFCT", food_group="Fruits")
    db.add(banana)
    db.flush()

    _run(db, usda_files)

    assert _value(db, banana.id, "iodine") is None


def test_curated_fish_ingredient_gets_iodine_from_usda(db, usda_files):
    """Seafood keeps its iodine pairing -- the animal concentrates iodine
    from its environment, so it isn't the exogenous-source concern milk and
    egg are."""
    seed_nutrients(db)
    tilapia = Ingredient(
        code="ifct:P083", name="Tilapia", source="IFCT", food_group="Marine Fish"
    )
    db.add(tilapia)
    db.flush()

    _run(db, usda_files)

    value = _value(db, tilapia.id, "iodine")
    assert value is not None
    assert value.per_100g == pytest.approx(4.145)
    assert value.source == "USDA"


def test_milk_gets_b12_but_no_iodine(db, usda_files):
    """Pins the ruling: US milk's iodine (37.9 ug/100g in this fixture,
    matching the real USDA value) is a processing artifact -- iodophor
    sanitisers on milking equipment, not a property of milk -- so it must
    never be attached even though B12 (genuinely synthesised by rumen
    bacteria) is."""
    seed_nutrients(db)
    milk = Ingredient(
        code="ifct:L002",
        name="Milk, whole, Cow",
        source="IFCT",
        food_group="Milk and Milk Products",
    )
    db.add(milk)
    db.flush()

    _run(db, usda_files)

    b12 = _value(db, milk.id, "vitamin_b12")
    assert b12 is not None
    assert b12.per_100g == pytest.approx(0.54)
    assert b12.source == "USDA"
    assert _value(db, milk.id, "iodine") is None


def test_egg_gets_b12_but_no_iodine(db, usda_files):
    """Same exogenous-source concern as milk: hen egg iodine tracks feed
    iodine-fortification programs, which are country/producer specific."""
    seed_nutrients(db)
    egg = Ingredient(
        code="ifct:M001",
        name="Egg, poultry, whole, raw",
        source="IFCT",
        food_group="Egg and Egg Products",
    )
    db.add(egg)
    db.flush()

    _run(db, usda_files)

    b12 = _value(db, egg.id, "vitamin_b12")
    assert b12 is not None
    assert b12.per_100g == pytest.approx(1.02)
    assert b12.source == "USDA"
    assert _value(db, egg.id, "iodine") is None


def test_running_twice_does_not_duplicate_rows(db, usda_files):
    seed_nutrients(db)
    banana = Ingredient(code="ifct:J001", name="Banana", source="IFCT", food_group="Fruits")
    tilapia = Ingredient(
        code="ifct:P083", name="Tilapia", source="IFCT", food_group="Marine Fish"
    )
    db.add_all([banana, tilapia])
    db.flush()

    first = _run(db, usda_files)
    second = _run(db, usda_files)

    assert first > 0
    assert second == 0
    assert db.query(IngredientNutrient).filter_by(ingredient_id=banana.id).count() == 1
    # tilapia opts into both nutrients, so it should gain exactly 2 rows.
    assert db.query(IngredientNutrient).filter_by(ingredient_id=tilapia.id).count() == 2
