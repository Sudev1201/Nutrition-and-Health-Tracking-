import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.common import to_canonical

IFCT_URL = (
    "https://raw.githubusercontent.com/ifct2017/compositions/master/compositions/index.csv"
)

# IFCT column -> (our nutrient code, the unit IFCT actually stores).
# Verified empirically: the mirror uses SI base units (g) and kJ, NOT the
# mg/ug/kcal printed in the book. Buffalo milk ca=0.121 is 121 mg.
IFCT_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "enerc": ("energy", "kj"),
    "protcnt": ("protein", "g"),
    "fatce": ("fat", "g"),
    "choavldf": ("carbohydrate", "g"),
    "fibtg": ("fibre", "g"),
    "cholc": ("cholesterol", "g"),
    "fasat": ("saturated_fat", "g"),
    "ca": ("calcium", "g"),
    "p": ("phosphorus", "g"),
    "mg": ("magnesium", "g"),
    "fe": ("iron", "g"),
    "zn": ("zinc", "g"),
    "se": ("selenium", "g"),
    "cu": ("copper", "g"),
    "mn": ("manganese", "g"),
    "k": ("potassium", "g"),
    "na": ("sodium", "g"),
    "vita": ("vitamin_a", "g"),
    "vitd": ("vitamin_d", "g"),
    "vite": ("vitamin_e", "g"),
    "vitk1": ("vitamin_k", "g"),
    "thia": ("thiamine", "g"),
    "ribf": ("riboflavin", "g"),
    "nia": ("niacin", "g"),
    "pantac": ("pantothenic_acid", "g"),
    "vitb6c": ("vitamin_b6", "g"),
    "biot": ("biotin", "g"),
    "folsum": ("folate", "g"),
    "vitc": ("vitamin_c", "g"),
    # Deliberately absent from IFCT: vitamin_b12, iodine. Sourced from USDA.
}


def load_ifct(db: Session, csv_path: Path) -> int:
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    existing = {i.code: i for i in db.scalars(select(Ingredient))}
    loaded = 0

    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            code = f"ifct:{row['code']}"
            ingredient = existing.get(code)

            if ingredient is None:
                ingredient = Ingredient(code=code, source="IFCT")
                db.add(ingredient)

            ingredient.name = row["name"]
            ingredient.food_group = row.get("grup") or None
            ingredient.diet_tags = row.get("tags") or None
            ingredient.search_aliases = row.get("lang") or None
            db.flush()

            for column, (nutrient_code, source_unit) in IFCT_COLUMN_MAP.items():
                raw = row.get(column)
                nutrient = nutrients.get(nutrient_code)
                if nutrient is None or raw in (None, "", "-"):
                    continue

                value = to_canonical(float(raw), source_unit, nutrient.unit)

                existing_value = db.scalar(
                    select(IngredientNutrient).where(
                        IngredientNutrient.ingredient_id == ingredient.id,
                        IngredientNutrient.nutrient_id == nutrient.id,
                    )
                )
                if existing_value is None:
                    db.add(
                        IngredientNutrient(
                            ingredient_id=ingredient.id,
                            nutrient_id=nutrient.id,
                            per_100g=value,
                            source="IFCT",
                        )
                    )
                else:
                    existing_value.per_100g = value

            loaded += 1

    db.flush()
    return loaded
