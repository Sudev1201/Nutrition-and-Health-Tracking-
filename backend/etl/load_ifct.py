import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.common import require_column_map, to_canonical

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
    # NOT a straight copy -- see _resolve_free_sugar. IFCT's `fsugar` is TOTAL
    # sugars; free sugar is a subset of it.
    "fsugar": ("free_sugar", "g"),
    # Deliberately absent from IFCT: vitamin_b12, iodine. Sourced from USDA.
}

# Foods whose total sugars ARE free sugars. WHO/ICMR define free sugars as all
# mono- and disaccharides added by manufacturer, cook or consumer, PLUS the
# sugars naturally present in honey, syrups and fruit juices. IFCT's Sugars
# group is exactly that: jaggery (ifct:I001, 84.32 g/100 g) and cane juice
# (ifct:I002, 12.85). IFCT has no honey or syrup row.
FREE_SUGAR_GROUPS = frozenset({"Sugars"})

# The one fruit-juice row outside that group. IFCT files "Lemon, juice" under
# Fruits, but a pressed juice is free sugar by the definition above, whole
# lemons are not. Named individually rather than by group precisely because
# the rest of the Fruits group must NOT be swept in with it.
FREE_SUGAR_CODES = frozenset({"E033"})

# Everything else gets an explicit zero, not a null. `fsugar` is populated for
# all 542 rows and is non-zero for 314 of them, but those are the food's own
# intrinsic sugars -- milk's lactose (4.89), an apple's fructose (9.53), even
# milled rice (0.69) -- and intrinsic sugars are categorically not free sugars.
# Copying the column wholesale would overstate free sugar across every fruit,
# vegetable and dairy food in the database, and would contradict the ruling
# already encoded for usda:curd, whose free-sugar row is 0 tagged
# derived:lactose-not-free.
#
# The zero is explicit for the same reason etl/load_usda.py writes an explicit
# zero for plant-source B12: free_sugar is an excess-sensitive tracked cap, and
# "this food has no free sugar" has to be distinguishable from "nobody looked".
# Only the second of those may ever suppress a cap.
#
# Two rows considered and deliberately left at the explicit zero:
# - ifct:K001 Toddy (5.73) and ifct:K002 Coconut water (3.06). Both are the
#   plant's own sap/liquid endosperm drunk as it comes, not a juice pressed
#   out of fruit flesh, so their sugars stay intrinsic.
INTRINSIC_SUGAR_SOURCE = "derived:intrinsic-sugar-zero"

# Oxalate class, spec 2026-08-15 design doc lines 437-441 and 545-546: total
# oxalate binds calcium in the gut, so "all keerai is calcium" is wrong.
# Absorption from spinach is ~5% against ~28-32% from milk, and plan 3's
# calcium maths has to be able to say so. "high" = high total (largely soluble)
# oxalate, calcium mostly unavailable; "low" = insoluble-oxalate-only greens
# whose calcium is genuinely usable.
#
# Deliberately small and explicit, in the same discipline as
# etl.load_usda.CURATED_ANIMAL_MAP: every entry is a food the spec names, and
# NULL keeps meaning "not classified", which the app must treat as unknown
# rather than as "low". IFCT has a row for every food the spec names; nothing
# was dropped for want of a code.
OXALATE_CLASS: dict[str, str] = {
    # High total oxalate. Arai/mulai keerai is Amaranthus -- all five IFCT
    # amaranth-leaf rows are the same genus and the same ruling applies to
    # each, so classifying only the one the recipes happen to use would leave
    # the other four reading as unclassified.
    "C002": "high",  # Amaranth leaves, green (arai keerai)
    "C003": "high",  # Amaranth leaves, red
    "C004": "high",  # Amaranth leaves, red and green
    "C005": "high",  # Amaranth, spinous, leaves, green (mulai keerai)
    "C006": "high",  # Amaranth, spinous, leaves, red and green
    "C033": "high",  # Spinach (palak)
    "C018": "high",  # Colocasia leaves, green
    # Insoluble oxalate only -- the greens that genuinely deliver calcium.
    "C019": "low",  # Drumstick leaves (murungai keerai)
    "C020": "low",  # Fenugreek leaves (methi)
    "G009": "low",  # Coriander leaves
    "G010": "low",  # Curry leaves
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


def _resolve_free_sugar(row: dict, nutrient: Nutrient) -> tuple[float, str] | None:
    """IFCT's total-sugar figure where total sugar IS free sugar, and an
    explicit, asserted zero everywhere else. See FREE_SUGAR_GROUPS.

    Returns None only when a free-sugar food publishes no figure at all, in
    which case free_sugar stays NULL -- unknown reads as unknown.
    """
    if row.get("grup") in FREE_SUGAR_GROUPS or row.get("code") in FREE_SUGAR_CODES:
        raw = row.get("fsugar")
        if raw in (None, "", "-"):
            return None
        return to_canonical(float(raw), "g", nutrient.unit), "IFCT"

    return 0.0, INTRINSIC_SUGAR_SOURCE


def load_ifct(db: Session, csv_path: Path) -> int:
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    existing = {i.code: i for i in db.scalars(select(Ingredient))}
    # Every (ingredient, nutrient) row already stored, read once. The previous
    # version issued one SELECT per nutrient per food -- 542 x 30 round trips
    # per load, which is where six minutes of this suite's runtime went.
    existing_values = {
        (value.ingredient_id, value.nutrient_id): value
        for value in db.scalars(select(IngredientNutrient))
    }
    loaded = 0

    with Path(csv_path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_column_map(
            "IFCT_COLUMN_MAP", IFCT_COLUMN_MAP, set(nutrients), set(reader.fieldnames or [])
        )

        for row in reader:
            code = f"ifct:{row['code']}"
            ingredient = existing.get(code)

            if ingredient is None:
                ingredient = Ingredient(code=code, source="IFCT")
                db.add(ingredient)

            ingredient.name = row["name"]
            ingredient.food_group = row.get("grup") or None
            ingredient.diet_tags = row.get("tags") or None
            ingredient.search_aliases = row.get("lang") or None
            ingredient.oxalate_class = OXALATE_CLASS.get(row["code"])
            db.flush()

            for column, (nutrient_code, source_unit) in IFCT_COLUMN_MAP.items():
                nutrient = nutrients[nutrient_code]

                # Two columns are not straight conversions: IFCT publishes
                # false zero energy for every oil and fat, and its sugar column
                # is total sugars where we track free sugars.
                if nutrient_code == "energy":
                    resolved = _resolve_energy(row, nutrient)
                elif nutrient_code == "free_sugar":
                    resolved = _resolve_free_sugar(row, nutrient)
                else:
                    raw = row.get(column)
                    resolved = (
                        None
                        if raw in (None, "", "-")
                        else (to_canonical(float(raw), source_unit, nutrient.unit), "IFCT")
                    )

                if resolved is None:
                    continue
                value, value_source = resolved

                existing_value = existing_values.get((ingredient.id, nutrient.id))
                if existing_value is None:
                    existing_values[(ingredient.id, nutrient.id)] = IngredientNutrient(
                        ingredient_id=ingredient.id,
                        nutrient_id=nutrient.id,
                        per_100g=value,
                        source=value_source,
                    )
                    db.add(existing_values[(ingredient.id, nutrient.id)])
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
