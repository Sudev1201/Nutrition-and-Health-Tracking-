import csv
from pathlib import Path
from typing import NamedTuple

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

# IFCT food groups that are exclusively plant foods. Vitamin B12 is
# synthesised only by bacteria/archaea and is genuinely absent from plant
# tissue -- writing an explicit 0.0 here is asserting a nutritional fact, not
# guessing a number. It is also what makes the app's vegetarian-observance
# compensation mean something: without an explicit zero, "no B12 row" and
# "this food has none" are indistinguishable, and a null can't drive a
# compensation rule the way a known zero can.
#
# "Miscellaneous Foods" (2 rows) is deliberately excluded: its composition
# isn't known well enough to assert it's plant-only.
PLANT_B12_ZERO_GROUPS = frozenset(
    {
        "Cereals and Millets",
        "Grain Legumes",
        "Green Leafy Vegetables",
        "Other Vegetables",
        "Fruits",
        "Roots and Tubers",
        "Nuts and Oil Seeds",
        "Condiments and Spices",
        "Edible Oils and Fats",
        "Sugars",
        "Mushrooms",
    }
)
PLANT_B12_ZERO_SOURCE = "derived:plant-b12-zero"


class CuratedPairing(NamedTuple):
    """One IFCT ingredient's pairing to a specific USDA food, and which of
    USDA_NUTRIENT_MAP's nutrients that pairing is trusted to supply.

    A single fdc_id is NOT assumed to supply both B12 and iodine -- see the
    intrinsic-vs-exogenous rule below CURATED_ANIMAL_MAP. `nutrients` lets
    each ingredient opt in per nutrient independently.
    """

    fdc_id: str
    nutrients: frozenset[str]


# Curated ifct-code -> USDA pairings, picked and verified by hand against the
# real etl/.cache/usda_foundation_food/FoodData_Central_foundation_food_csv_2025-04-24/
# food.csv, not matched by algorithm. This replaces a prior version of this
# loader that fuzzy-matched IFCT names against USDA descriptions by first
# comma-separated word; against the real data that matched ~5% of
# ingredients and produced wrong pairings -- notably attaching the same
# American "MILK, 2% (WAVE 22E)" row to BOTH "Milk, whole, Buffalo" and
# "Milk, whole, Cow", two distinct Indian foods collapsed onto one Western
# row. A wrong value that looks authoritative is worse than a null, so this
# map is deliberately small and every entry is auditable below. Everything
# in an animal food group that isn't listed here stays NULL.
#
# THE INTRINSIC-VS-EXOGENOUS RULE for which nutrients a pairing may supply:
# B12 is synthesised by the animal (rumen bacteria in cattle) or is a fixed
# biological consequence of what the species is, so a USDA sample's B12
# value is a property of the food and transfers across countries reasonably
# well. Iodine is frequently NOT like this -- it can be a residue of a
# specific country's production practice rather than the food itself:
# - US dairy iodine is inflated by iodophor sanitisers used on milking
#   equipment and teat dips, a US processing practice, not a property of
#   milk. It does not transfer to Indian cow milk.
# - Hen egg iodine tracks feed iodine-fortification programs, which are
#   country- and producer-specific, for the same reason -- excluded here too.
# - Seafood iodine is different in kind: fish and shellfish concentrate
#   iodine from seawater/marine algae through their own physiology. The
#   iodine is genuinely IN the animal, not a processing artifact, so marine
#   and freshwater fish keep their iodine pairing.
# The next person extending this map should apply the same test per nutrient,
# not assume one fdc_id is good for everything USDA happens to report on it.
#
# Foods considered and rejected, for the record:
# - ifct:L001 Milk, whole, Buffalo: NOT mapped. USDA's foundation-food set
#   has no water-buffalo milk at all (the US dairy industry is essentially
#   all-cow); every candidate would be cow milk wearing a buffalo's name.
# - ifct:L003 Paneer: NOT mapped. Closest USDA entries are Cheese, ricotta,
#   whole milk (fdc 323444, a whey cheese from a different process), Cheese,
#   dry white, queso seco (fdc 329830, aged and salted), and Cheese, queso
#   fresco, solid (fdc 2647442, no B12 value recorded at all). None is a
#   confident stand-in for unsalted, unaged, acid-set Indian paneer. A poor
#   analog is worse than no analog, so this stays a deliberate gap.
# - ifct:P009 Cat fish (Marine Fish): NOT mapped. USDA's farmed catfish is
#   the freshwater species (Ictaluridae); IFCT's marine "Cat fish" is a
#   different, unrelated family (Ariidae) that only shares an English name.
#   See ifct:S001 below for the freshwater one, which USDA's entry does match.
# - ifct:P084 Tuna (Marine Fish): NOT mapped. The only USDA foundation-food
#   tuna is "canned in water, drained solids" -- a different, processed
#   preparation from IFCT's raw fish values, not a confident match.
CURATED_ANIMAL_MAP: dict[str, CuratedPairing] = {
    # Milk and Milk Products. B12 only -- see the intrinsic-vs-exogenous
    # rule above: USDA's 37.9 ug/100g iodine reflects US teat-dip/sanitiser
    # residue, not milk composition.
    "ifct:L002": CuratedPairing(
        "322892", frozenset({"vitamin_b12"})
    ),  # Milk, whole, 3.25% milkfat, with added vitamin D
    # Egg and Egg Products. B12 only -- hen egg iodine tracks feed
    # iodine-fortification programs (country/producer specific), the same
    # exogenous-source concern as milk.
    "ifct:M001": CuratedPairing(
        "748967", frozenset({"vitamin_b12"})
    ),  # Eggs, Grade A, Large, egg whole
    # Marine Fish. Both nutrients -- seafood iodine is concentrated by the
    # animal itself, not a processing artifact.
    "ifct:P068": CuratedPairing(
        "2684441", frozenset({"vitamin_b12", "iodine"})
    ),  # Fish, salmon, Atlantic, farm raised, raw
    "ifct:P083": CuratedPairing(
        "2684442", frozenset({"vitamin_b12", "iodine"})
    ),  # Fish, tilapia, farm raised, raw
    # Fresh Water Fish and Shellfish. Both nutrients, same reasoning.
    "ifct:S001": CuratedPairing(
        "2684445", frozenset({"vitamin_b12", "iodine"})
    ),  # Fish, catfish, farm raised, raw
}


def _existing(db: Session, ingredient_id, nutrient_id) -> IngredientNutrient | None:
    return db.scalar(
        select(IngredientNutrient).where(
            IngredientNutrient.ingredient_id == ingredient_id,
            IngredientNutrient.nutrient_id == nutrient_id,
        )
    )


def _zero_fill_plant_b12(
    db: Session, ingredients_by_code: dict[str, Ingredient], nutrients: dict[str, Nutrient]
) -> int:
    """Plant-source B12 is zero, not missing (see PLANT_B12_ZERO_GROUPS)."""
    b12 = nutrients.get("vitamin_b12")
    if b12 is None:
        return 0

    written = 0
    for ingredient in ingredients_by_code.values():
        if ingredient.food_group not in PLANT_B12_ZERO_GROUPS:
            continue
        if _existing(db, ingredient.id, b12.id) is not None:
            continue  # never overwrite an existing value

        db.add(
            IngredientNutrient(
                ingredient_id=ingredient.id,
                nutrient_id=b12.id,
                per_100g=0.0,
                source=PLANT_B12_ZERO_SOURCE,
            )
        )
        written += 1

    db.flush()
    return written


def _fill_curated_animal(
    db: Session,
    ingredients_by_code: dict[str, Ingredient],
    nutrients: dict[str, Nutrient],
    food_csv: Path,
    nutrient_csv: Path,
    food_nutrient_csv: Path,
) -> int:
    """Animal-source B12 and iodine come only from CURATED_ANIMAL_MAP, and
    only for the nutrients each pairing explicitly opts into (see the
    intrinsic-vs-exogenous rule above the map -- a fdc_id having a USDA value
    for a nutrient is not by itself enough to attach it).

    Iodine gets no zero-fill (plant iodine is soil-dependent, not reliably
    zero) -- it is only ever attached here, for the pairings that opted in,
    when USDA actually records a value for that food.
    """
    wanted_fdc_ids = {pairing.fdc_id for pairing in CURATED_ANIMAL_MAP.values()}
    fdc_to_ifct = {pairing.fdc_id: code for code, pairing in CURATED_ANIMAL_MAP.items()}

    # A curated fdc_id has to actually exist in the supplied food.csv. This
    # guards against a stale mapping (e.g. a future USDA release renumbering
    # or dropping a food) silently attaching a value to the wrong row --
    # instead it is simply skipped, staying NULL like everything else
    # unmapped.
    known_fdc_ids: set[str] = set()
    with Path(food_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["fdc_id"] in wanted_fdc_ids:
                known_fdc_ids.add(row["fdc_id"])

    units: dict[str, str] = {}
    with Path(nutrient_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["id"] in USDA_NUTRIENT_MAP:
                units[row["id"]] = row["unit_name"].lower()

    written = 0
    with Path(food_nutrient_csv).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            fdc_id = row["fdc_id"]
            if fdc_id not in wanted_fdc_ids or fdc_id not in known_fdc_ids:
                continue

            nutrient_code = USDA_NUTRIENT_MAP.get(row["nutrient_id"])
            if nutrient_code is None:
                continue

            ifct_code = fdc_to_ifct[fdc_id]
            if nutrient_code not in CURATED_ANIMAL_MAP[ifct_code].nutrients:
                continue  # this pairing doesn't vouch for this nutrient

            ingredient = ingredients_by_code.get(ifct_code)
            nutrient = nutrients.get(nutrient_code)
            if ingredient is None or nutrient is None:
                continue
            if _existing(db, ingredient.id, nutrient.id) is not None:
                continue  # never overwrite an existing value

            db.add(
                IngredientNutrient(
                    ingredient_id=ingredient.id,
                    nutrient_id=nutrient.id,
                    per_100g=to_canonical(
                        float(row["amount"]),
                        units.get(row["nutrient_id"], "ug"),
                        nutrient.unit,
                    ),
                    source="USDA",
                )
            )
            written += 1

    db.flush()
    return written


def load_usda_gapfill(
    db: Session, food_csv: Path, nutrient_csv: Path, food_nutrient_csv: Path
) -> int:
    """Attach vitamin_b12 and iodine where IFCT has neither.

    Two distinct rules, not one fuzzy match:
    - every ingredient in a pure-plant food group gets an explicit B12 of
      0.0 (PLANT_B12_ZERO_GROUPS / PLANT_B12_ZERO_SOURCE);
    - a small, hand-verified set of animal foods (CURATED_ANIMAL_MAP) gets
      B12 and/or iodine from a specific named USDA row, per-nutrient, per
      the intrinsic-vs-exogenous rule documented above the map.
    Everything else stays NULL -- unknown must read as unknown. An existing
    IngredientNutrient row is never overwritten; IFCT is the authority for
    Indian foods where it has data.
    """
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    ingredients_by_code = {i.code: i for i in db.scalars(select(Ingredient))}

    written = _zero_fill_plant_b12(db, ingredients_by_code, nutrients)
    written += _fill_curated_animal(
        db, ingredients_by_code, nutrients, food_csv, nutrient_csv, food_nutrient_csv
    )
    return written
