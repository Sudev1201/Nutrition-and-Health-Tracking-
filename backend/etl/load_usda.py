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


SR_LEGACY_SOURCE = "USDA:SR-legacy"


class CuratedPairing(NamedTuple):
    """One IFCT ingredient's pairing to a specific USDA food, and which of
    USDA_NUTRIENT_MAP's nutrients that pairing is trusted to supply.

    A single fdc_id is NOT assumed to supply both B12 and iodine -- see the
    intrinsic-vs-exogenous rule below CURATED_ANIMAL_MAP. `nutrients` lets
    each ingredient opt in per nutrient independently.
    """

    fdc_id: str
    nutrients: frozenset[str]


class LegacyPairing(NamedTuple):
    """A pairing to a USDA Standard Reference Legacy row, and the values
    transcribed from it.

    Unlike CuratedPairing there is no local CSV to read -- SR Legacy is not
    part of the Foundation download -- so the numbers live in the source, each
    beside the fdc_id and description it came from. See LEGACY_ANIMAL_MAP.
    """

    fdc_id: str
    description: str
    values: tuple[tuple[str, float, str], ...]  # (nutrient code, value, unit)


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
#   preparation from IFCT's raw fish values, not a confident match. No recipe
#   uses it, so it is left alone rather than reopened against SR Legacy.
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
    # Poultry. B12 only -- poultry iodine tracks feed iodine supplementation,
    # the same exogenous-source concern as hen egg and cow milk.
    #
    # Preparation caveat, stated rather than hidden: IFCT's N001 is raw leg,
    # and this is the ONLY chicken row in the whole Foundation release that
    # reports B12 at all (the eight raw chicken rows report none). Braising
    # drives off water, so 0.41 ug/100 g is a modest overstatement of the raw
    # basis -- against a dish that currently reports a confident, fully wrong
    # 0.0, and 0.41 is small enough that the error is a rounding difference on
    # a 2.4 ug/day requirement.
    "ifct:N001": CuratedPairing(
        "331897", frozenset({"vitamin_b12"})
    ),  # Chicken, broilers or fryers, drumstick, meat only, cooked, braised
}

# Species the Foundation release does not carry AT ALL, paired instead to USDA
# Standard Reference Legacy and transcribed here, exactly as
# etl/load_manual_ingredients.py does for the five non-IFCT ingredients, and
# tagged SR_LEGACY_SOURCE so a reader can always tell which release a number
# came from.
#
# Why this exists: task 6 chose the fish South Indian households actually buy,
# and Foundation's entire finfish set is haddock, pollock, canned tuna, two
# salmon, tilapia, cod and catfish -- no mackerel, no anchovy, no sardine, no
# seer, under any spelling. Every ingredient in those dishes carries an
# explicit derived:plant-b12-zero, so with the fish contributing nothing the
# eight fish dishes summed to a hard 0.0 ug of B12: filter coffee out-scored
# fish curry on the nutrient fish is this cuisine's principal source of, and
# B12 is what drives the vegetarian-observance compensation rule.
#
# Selection rule applied to each, in order: closest species (genus, then
# family), then the same preparation basis as IFCT (raw), then -- where two
# real rows remain and disagree -- the LOWER figure. Overstating B12 tells a
# short user they are fine, which is the dangerous direction; understating it
# only offers compensation that was not needed.
#
# Values retrieved 2026-08-17 from https://api.nal.usda.gov/fdc/v1/foods/search
# (dataType=SR Legacy). SR Legacy reports no iodine for any finfish, so these
# pairings supply B12 only -- not a judgement about seafood iodine, which the
# intrinsic-vs-exogenous rule above still permits; there is simply no number.
LEGACY_ANIMAL_MAP: dict[str, LegacyPairing] = {
    # Rastrelliger kanagurta, Indian mackerel: a small oily Scombrid, same
    # tribe (Scombrini) as Atlantic mackerel, and raw. USDA's "mackerel,
    # Pacific and jack, mixed species, raw" (4.4) was rejected despite being
    # the lower figure because it blends in jack mackerel, a Carangid -- a
    # different family. Species first, per the rule above.
    "ifct:P034": LegacyPairing(
        "175119", "Fish, mackerel, Atlantic, raw", (("vitamin_b12", 8.71, "ug"),)
    ),
    # Stolephorus indicus, Indian anchovy -> Engraulis encrasicolus, European
    # anchovy. Same family (Engraulidae), raw, and SR Legacy's only raw
    # anchovy row. The canned-in-oil row (0.88) is a processed basis.
    "ifct:P003": LegacyPairing(
        "174182", "Fish, anchovy, european, raw", (("vitamin_b12", 0.62, "ug"),)
    ),
    # Sardinella longiceps, Indian oil sardine. The one pairing here that is
    # NOT raw: SR Legacy has no raw sardine at all, only two canned rows.
    # Chosen over the raw Clupeids that were the alternative -- herring,
    # Atlantic, raw (13.7) and herring, Pacific, raw (10.0) -- because a
    # sardine is the same fish type and those are not, and because both of
    # them read HIGHER, so this is the conservative choice of the three rather
    # than the flattering one. Canning in oil and draining concentrates
    # per-100 g values against a raw basis, so if 8.94 is wrong for Indian oil
    # sardine it is wrong on the high side; that is stated here rather than
    # left for a reader to discover.
    "ifct:P071": LegacyPairing(
        "175139",
        "Fish, sardine, Atlantic, canned in oil, drained solids with bone",
        (("vitamin_b12", 8.94, "ug"),),
    ),
    # Scomberomorus commerson, vanjaram/seer. SR Legacy has two raw rows in
    # the SAME genus and they disagree by 6.5x: king (S. cavalla, 15.6) and
    # spanish (S. maculatus, 2.4). Genus does not separate them, so the
    # tiebreak is the name -- FAO's English name for S. commerson is
    # "narrow-barred Spanish mackerel" -- and then the lower figure. Both
    # candidates are recorded here because the choice is a judgement, not a
    # lookup, and a later reader may have better grounds to revisit it.
    "ifct:P087": LegacyPairing(
        "173673", "Fish, mackerel, spanish, raw", (("vitamin_b12", 2.4, "ug"),)
    ),
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


def _fill_legacy_animal(
    db: Session,
    ingredients_by_code: dict[str, Ingredient],
    nutrients: dict[str, Nutrient],
) -> int:
    """Write the SR Legacy pairings for the species Foundation does not carry.

    Same two rules as everything else here: never overwrite an existing value,
    and never invent one -- an ifct code with no entry in LEGACY_ANIMAL_MAP
    stays NULL.
    """
    written = 0
    for ifct_code, pairing in LEGACY_ANIMAL_MAP.items():
        ingredient = ingredients_by_code.get(ifct_code)
        if ingredient is None:
            continue

        for nutrient_code, value, unit in pairing.values:
            nutrient = nutrients.get(nutrient_code)
            if nutrient is None:
                continue
            if _existing(db, ingredient.id, nutrient.id) is not None:
                continue

            db.add(
                IngredientNutrient(
                    ingredient_id=ingredient.id,
                    nutrient_id=nutrient.id,
                    per_100g=to_canonical(value, unit, nutrient.unit),
                    source=SR_LEGACY_SOURCE,
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
      the intrinsic-vs-exogenous rule documented above the map;
    - the species Foundation does not carry at all (LEGACY_ANIMAL_MAP) get
      B12 from a named SR Legacy row, transcribed in this file.
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
    written += _fill_legacy_animal(db, ingredients_by_code, nutrients)
    return written
