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

# Atwater general factors, kcal per gram of each macronutrient.
ATWATER_KCAL_PER_G: dict[str, float] = {
    "protcnt": 4.0,  # protein
    "choavldf": 4.0,  # available carbohydrate
    "fatce": 9.0,  # fat
}
ATWATER_SOURCE = "derived:atwater"

# Below this, a published zero is plausibly the truth -- water, and spices whose
# trace macros round to nothing. Above it, a zero contradicts the food's own
# macro row and is a data defect. 20 kcal/100 g is well clear of both.
ATWATER_MIN_KCAL = 20.0


def _atwater_kcal(row: dict) -> float:
    """kcal per 100 g implied by the row's OWN protein, carbohydrate and fat."""
    total = 0.0
    for column, factor in ATWATER_KCAL_PER_G.items():
        raw = row.get(column)
        if raw in (None, "", "-"):
            continue
        total += float(raw) * factor
    return total


def _resolve_energy(row: dict, nutrient: Nutrient) -> tuple[float, str] | None:
    """IFCT's own energy figure, or an Atwater derivation where that figure is a
    false zero.

    All 14 rows of IFCT's "Edible Oils and Fats" group -- every cooking oil plus
    ghee and vanaspati -- publish `enerc=0` alongside `fatce=100`. That is a
    defect in the source, not a fact about oil: 100 g of fat is ~900 kcal by
    definition. Taken at face value it silently zeroes the calories of the single
    most energy-dense thing in the pantry, and because nearly all South Indian
    cooking is oil-tempered it understates 40+ authored dishes by 30-112%.

    So: trust IFCT wherever it publishes a non-zero figure, and fall back to the
    row's own macros where it publishes a zero that its own macros contradict.
    The derived rows are tagged ATWATER_SOURCE rather than "IFCT" so the
    substitution is visible in reports and can never be mistaken for a measured
    value -- the same convention etl/load_usda.py uses for its derived zeros.

    Returns None only when there is neither a published figure nor enough macro
    detail to derive one, in which case energy stays NULL.
    """
    raw = row.get("enerc")
    published = (
        None if raw in (None, "", "-") else to_canonical(float(raw), "kj", nutrient.unit)
    )

    if published is not None and published > 0:
        return published, "IFCT"

    implied = _atwater_kcal(row)
    if implied > ATWATER_MIN_KCAL:
        return implied, ATWATER_SOURCE

    # A genuine zero (or near-zero) stays a genuine zero.
    return None if published is None else (published, "IFCT")


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
                nutrient = nutrients.get(nutrient_code)
                if nutrient is None:
                    continue

                # Energy is the one column that is not a straight conversion --
                # IFCT publishes false zeros for every oil and fat.
                if nutrient_code == "energy":
                    resolved = _resolve_energy(row, nutrient)
                    if resolved is None:
                        continue
                    value, value_source = resolved
                else:
                    raw = row.get(column)
                    if raw in (None, "", "-"):
                        continue
                    value = to_canonical(float(raw), source_unit, nutrient.unit)
                    value_source = "IFCT"

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
                            source=value_source,
                        )
                    )
                else:
                    existing_value.per_100g = value
                    # Re-running has to be able to CORRECT a row, provenance
                    # included: the database already holds oils at 0 kcal
                    # tagged "IFCT", and those rows must end up
                    # derived:atwater, not merely re-zeroed.
                    existing_value.source = value_source

            loaded += 1

    db.flush()
    return loaded
