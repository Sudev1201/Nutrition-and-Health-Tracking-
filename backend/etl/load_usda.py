import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.common import to_canonical

USDA_URL = (
    "https://fdc.nal.usda.gov/fdc-datasets/"
    "FoodData_Central_foundation_food_csv_2025-04-24.zip"
)

# USDA nutrient id -> our nutrient code. Only the two IFCT omits.
USDA_NUTRIENT_MAP = {
    "1178": "vitamin_b12",
    "1100": "iodine",
}


def _normalise(name: str) -> str:
    """Reduce a food name to its first significant word for matching."""
    return name.lower().split(",")[0].strip()


def load_usda_gapfill(
    db: Session, food_csv: Path, nutrient_csv: Path, food_nutrient_csv: Path
) -> int:
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    ingredients = list(db.scalars(select(Ingredient)))
    by_key: dict[str, Ingredient] = {}
    for ingredient in ingredients:
        by_key.setdefault(_normalise(ingredient.name), ingredient)

    units = {}
    with Path(nutrient_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            units[row["id"]] = row["unit_name"].lower()

    foods = {}
    with Path(food_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            foods[row["fdc_id"]] = row["description"]

    filled = 0
    with Path(food_nutrient_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = USDA_NUTRIENT_MAP.get(row["nutrient_id"])
            if code is None:
                continue

            description = foods.get(row["fdc_id"])
            ingredient = by_key.get(_normalise(description or ""))
            nutrient = nutrients.get(code)
            if ingredient is None or nutrient is None:
                continue

            already = db.scalar(
                select(IngredientNutrient).where(
                    IngredientNutrient.ingredient_id == ingredient.id,
                    IngredientNutrient.nutrient_id == nutrient.id,
                )
            )
            if already is not None:
                continue  # IFCT wins for Indian foods.

            db.add(
                IngredientNutrient(
                    ingredient_id=ingredient.id,
                    nutrient_id=nutrient.id,
                    per_100g=to_canonical(
                        float(row["amount"]), units.get(row["nutrient_id"], "ug"), nutrient.unit
                    ),
                    source="USDA",
                )
            )
            filled += 1

    db.flush()
    return filled
