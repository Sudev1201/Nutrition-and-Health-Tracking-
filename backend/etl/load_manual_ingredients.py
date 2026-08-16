"""The five ingredients no IFCT row can supply, without which the recipe set is unusable.

Forty of the sixty-six authored South Indian dishes contain salt and nothing
else from this file; until salt exists, every sodium number the app produces is
wrong, and sodium is the nutrient the whole hypertension rule set acts on. The
other four (curd, sugar, brewed coffee, brewed tea) are each used by between one
and five dishes and are equally unavailable from IFCT -- IFCT's Sugars group
holds only jaggery and cane juice, its Milk group only buffalo milk, cow milk,
paneer and khoa, and it has no beverage group at all.

Every value below is transcribed from a named, citable row. Nothing here is a
guess, and each IngredientNutrient carries its own `source` tag so a mixed-
provenance ingredient (salt, curd) stays auditable per nutrient rather than
per food.

Sources
-------
USDA FoodData Central is CC0 and cited by fdc_id throughout. Two release
channels are used and tagged differently:

* ``USDA`` -- the Foundation Foods release already downloaded to
  ``etl/.cache/usda_foundation_food/FoodData_Central_foundation_food_csv_2025-04-24/``
  and read directly out of ``food.csv`` / ``food_nutrient.csv`` / ``nutrient.csv``
  for this file. Foundation rows are the newer, more completely analysed
  samples, so they are preferred wherever they exist.
* ``USDA:SR-legacy`` -- Standard Reference Legacy, retrieved 2026-08-16 from
  ``https://api.nal.usda.gov/fdc/v1/foods``. Used only to fill nutrients the
  Foundation row does not report at all, and only from a Legacy row describing
  the *same food* under the same name. Tagged distinctly so a later reader can
  tell which numbers came from the modern analysis and which did not.

The two non-USDA tags:

* ``FSSAI-2018`` -- Food Safety and Standards (Fortification of Foods)
  Regulations, 2018, Schedule I, which sets iodised salt at not less than
  30 ppm iodine at the point of manufacture and not less than 15 ppm at the
  retail/consumer level, on a dry weight basis. India's fortification level is
  a national regulation, not a property of sodium chloride, so it is tagged
  separately from the USDA composition it overrides. (Noted for honesty, in the
  style of etl/load_reference.py: the regulation text itself was not re-fetched
  in this session -- fssai.gov.in was unreachable and the search budget was
  exhausted -- so this is the figure as specified in the product ruling for
  this task, matched to the regulation that publishes it.)
* ``derived:...`` -- an explicit zero that asserts a nutritional fact rather
  than copying a measurement, exactly as etl/load_usda.py does for plant-source
  B12. See each use below for the fact being asserted.

The two deliberate departures from the USDA row (both are the SAME
intrinsic-vs-exogenous rule that etl/load_usda.py already applies, so they are
consistent with, not exceptions to, how this codebase treats foreign data):

1. ``manual:salt`` takes its iodine from FSSAI, not from USDA's 5,080 ug/100 g.
   USDA's figure is the US fortification level (~50 ppm); India mandates 15 ppm
   at retail. Iodine in salt is a policy number, and the wrong country's policy
   would overstate a hypertensive user's iodine by 3.4x.
2. ``usda:curd`` drops USDA's iodine entirely (32.33 ug/100 g). US dairy iodine
   is largely iodophor sanitiser and teat-dip residue from US milking practice,
   not a property of milk -- this is precisely why
   ``etl.load_usda.CURATED_ANIMAL_MAP`` pairs ifct:L002 cow milk for B12 only
   and refuses its iodine. Indian curd inherits the same refusal, and iodine
   stays NULL rather than being invented.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.common import to_canonical

USDA = "USDA"
SR_LEGACY = "USDA:SR-legacy"
FSSAI = "FSSAI-2018"

# Explicit-zero tags. Each asserts a fact about the food, not a measurement.
NO_ORGANICS = "derived:mineral-no-organics"  # sodium chloride has no organic fraction
NO_FIBRE = "derived:dairy-no-fibre"  # milk and its ferments contain no fibre
NOT_FREE_SUGAR = "derived:lactose-not-free"  # lactose is intrinsic, not a free sugar
NO_SUGAR_BEVERAGE = "derived:unsweetened"  # nothing is added to a plain infusion


@dataclass(frozen=True)
class NutrientValue:
    """One nutrient of one manual ingredient, in the unit its source publishes."""

    code: str
    value: float
    unit: str
    source: str


@dataclass(frozen=True)
class ManualIngredient:
    code: str
    name: str
    source: str
    food_group: str
    diet_tags: str
    nutrients: tuple[NutrientValue, ...]


VEG_TAGS = "vegetarian eggetarian fishetarian veg"


# ---------------------------------------------------------------------------
# 1. manual:salt -- iodised table salt
#
# Composition: USDA FoodData Central Foundation Foods, fdc_id 746775,
# "Salt, table, iodized" (published 2019-12-16; the identical earlier sample is
# fdc_id 321505). Read out of the local Foundation CSV cache. It reports
# sodium 38,700 mg, calcium 50 mg, potassium 2 mg, manganese 0.032 mg per 100 g,
# zero for magnesium/phosphorus/iron/zinc/copper, and 0 kcal.
#
# Cross-check on the sodium figure, which is the single most load-bearing
# number in the whole recipe set: sodium chloride is 39.34% sodium by mass --
# Na 22.98977 / NaCl 58.44277 = 0.39337, from the IUPAC Commission on Isotopic
# Abundances and Atomic Weights standard atomic weights (Na 22.98976928(2),
# Cl 35.45). Pure NaCl would therefore be 39,337 mg Na per 100 g. USDA's 38,700
# is 98.4% of that, which is exactly what a real retail salt is: USDA's own row
# records 0.42 g water and 99 g ash per 100 g, the balance being anticaking
# agent and the iodate itself. So 38,700 is the right number for salt as
# actually eaten, and 39,337 would be the number for a reagent bottle.
#
# Iodine is the one value NOT taken from USDA -- see the module docstring's
# departure (1). 15 ppm = 15 mg/kg = 1,500 ug per 100 g.
# ---------------------------------------------------------------------------
SALT = ManualIngredient(
    code="manual:salt",
    name="Salt, iodised",
    # "manual", not "USDA": no single USDA row describes Indian iodised salt.
    # This is a USDA composition with an Indian regulatory iodine substituted in.
    source="manual",
    food_group="Condiments and Spices",
    diet_tags=VEG_TAGS,
    nutrients=(
        NutrientValue("sodium", 38700.0, "mg", USDA),
        NutrientValue("iodine", 1500.0, "ug", FSSAI),
        NutrientValue("calcium", 50.0, "mg", USDA),
        NutrientValue("potassium", 2.0, "mg", USDA),
        NutrientValue("manganese", 0.032, "mg", USDA),
        NutrientValue("magnesium", 0.0, "mg", USDA),
        NutrientValue("phosphorus", 0.0, "mg", USDA),
        NutrientValue("iron", 0.0, "mg", USDA),
        NutrientValue("zinc", 0.0, "mg", USDA),
        NutrientValue("copper", 0.0, "mg", USDA),
        NutrientValue("energy", 0.0, "kcal", USDA),
        # Salt is an inorganic solid. It contains no protein, fat, carbohydrate
        # or vitamin, and writing that as an explicit zero (rather than leaving
        # it NULL) is asserting chemistry, not guessing a value -- the same
        # distinction etl/load_usda.py draws for plant-source B12.
        NutrientValue("protein", 0.0, "g", NO_ORGANICS),
        NutrientValue("fat", 0.0, "g", NO_ORGANICS),
        NutrientValue("saturated_fat", 0.0, "g", NO_ORGANICS),
        NutrientValue("carbohydrate", 0.0, "g", NO_ORGANICS),
        NutrientValue("free_sugar", 0.0, "g", NO_ORGANICS),
        NutrientValue("fibre", 0.0, "g", NO_ORGANICS),
        NutrientValue("cholesterol", 0.0, "mg", NO_ORGANICS),
        NutrientValue("vitamin_a", 0.0, "ug", NO_ORGANICS),
        NutrientValue("vitamin_d", 0.0, "ug", NO_ORGANICS),
        NutrientValue("vitamin_e", 0.0, "mg", NO_ORGANICS),
        NutrientValue("vitamin_k", 0.0, "ug", NO_ORGANICS),
        NutrientValue("thiamine", 0.0, "mg", NO_ORGANICS),
        NutrientValue("riboflavin", 0.0, "mg", NO_ORGANICS),
        NutrientValue("niacin", 0.0, "mg", NO_ORGANICS),
        NutrientValue("pantothenic_acid", 0.0, "mg", NO_ORGANICS),
        NutrientValue("vitamin_b6", 0.0, "mg", NO_ORGANICS),
        NutrientValue("biotin", 0.0, "ug", NO_ORGANICS),
        NutrientValue("folate", 0.0, "ug", NO_ORGANICS),
        NutrientValue("vitamin_b12", 0.0, "ug", NO_ORGANICS),
        NutrientValue("vitamin_c", 0.0, "mg", NO_ORGANICS),
        # selenium: USDA does not report it for salt. Left NULL on purpose.
    ),
)


# ---------------------------------------------------------------------------
# 2. usda:curd -- plain whole-milk yoghurt, standing in for Indian dahi
#
# Primary: USDA FoodData Central Foundation Foods, fdc_id 2259793,
# "Yogurt, plain, whole milk" (published 2022-04-28), read out of the local
# Foundation CSV cache. This is a genuine, exact-name match -- no derivation
# from cow milk was needed. Energy is nutrient 2048, "Energy (Atwater Specific
# Factors)", 77.32 kcal/100 g (the general-factors figure is 77.95).
#
# Gap-fill: USDA SR Legacy fdc_id 171284, "Yogurt, plain, whole milk"
# (NDB 01116) supplies the seven nutrients the Foundation row simply does not
# carry -- vitamin A, E and C, folate, B12, pantothenic acid and selenium. B12
# in particular matters: curd is one of the few B12 sources a lacto-vegetarian
# eats daily, and leaving it NULL would silently zero the app's B12 story for
# curd rice, more kuzhambu, avial, neer mor and the plain-curd side.
#
# Iodine deliberately dropped -- see the module docstring's departure (2).
#
# Caveat for the record: Indian dahi is set from milk that is typically boiled
# and often buffalo, and is soured further than a US retail yoghurt. Protein
# and fat therefore sit a little low here relative to a home-set thick curd,
# and lactose a little high. A published Indian curd composition would be
# better; none exists in IFCT, and a real named USDA row beats a hand-derivation
# from ifct:L002 with the carbohydrate fudged, which was the alternative.
# ---------------------------------------------------------------------------
CURD = ManualIngredient(
    code="usda:curd",
    name="Curd (dahi), plain, whole milk",
    source="USDA",
    food_group="Milk and Milk Products",
    diet_tags=VEG_TAGS,
    nutrients=(
        # --- USDA Foundation 2259793 ---
        NutrientValue("energy", 77.32, "kcal", USDA),
        NutrientValue("protein", 3.824, "g", USDA),
        NutrientValue("fat", 4.484, "g", USDA),
        NutrientValue("saturated_fat", 2.316, "g", USDA),
        NutrientValue("carbohydrate", 5.575, "g", USDA),
        NutrientValue("cholesterol", 14.17, "mg", USDA),
        NutrientValue("calcium", 126.8, "mg", USDA),
        NutrientValue("phosphorus", 101.2, "mg", USDA),
        NutrientValue("magnesium", 11.45, "mg", USDA),
        NutrientValue("iron", 0.0, "mg", USDA),
        NutrientValue("zinc", 0.4283, "mg", USDA),
        NutrientValue("copper", 0.003175, "mg", USDA),
        NutrientValue("manganese", 0.001539, "mg", USDA),
        NutrientValue("potassium", 164.1, "mg", USDA),
        NutrientValue("sodium", 41.78, "mg", USDA),
        NutrientValue("vitamin_d", 0.778, "ug", USDA),
        NutrientValue("vitamin_k", 0.2, "ug", USDA),
        NutrientValue("thiamine", 0.05519, "mg", USDA),
        NutrientValue("riboflavin", 0.2431, "mg", USDA),
        NutrientValue("niacin", 0.135, "mg", USDA),
        NutrientValue("vitamin_b6", 0.04506, "mg", USDA),
        NutrientValue("biotin", 0.0, "ug", USDA),
        # --- USDA SR Legacy 171284, only where Foundation reports nothing ---
        NutrientValue("vitamin_a", 27.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_e", 0.06, "mg", SR_LEGACY),
        NutrientValue("vitamin_c", 0.5, "mg", SR_LEGACY),
        NutrientValue("folate", 7.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_b12", 0.37, "ug", SR_LEGACY),
        NutrientValue("pantothenic_acid", 0.389, "mg", SR_LEGACY),
        NutrientValue("selenium", 2.2, "ug", SR_LEGACY),
        # --- asserted facts ---
        NutrientValue("fibre", 0.0, "g", NO_FIBRE),
        # Foundation records 4.09 g total sugars, of which 3.35 g is lactose and
        # 0.75 g galactose -- all of it milk's own sugar. Under the WHO/ICMR
        # definition free sugars exclude the lactose naturally present in milk
        # and milk products, so plain curd has none.
        NutrientValue("free_sugar", 0.0, "g", NOT_FREE_SUGAR),
        # iodine: deliberately absent.
    ),
)


# ---------------------------------------------------------------------------
# 3. manual:sugar -- white granulated sugar (sucrose)
#
# USDA SR Legacy fdc_id 169655, "Sugars, granulated" (NDB 19335), retrieved
# 2026-08-16. Not present in the Foundation release, so Legacy is the best
# available cited row and every value carries the SR_LEGACY tag.
#
# 99.98 g carbohydrate and 387 kcal per 100 g. The task brief's "~100 g carb,
# ~400 kcal" is the round-number version of exactly this row; 387 is used rather
# than 400 because it is the published figure (sucrose at 3.87 kcal/g, the
# Atwater factor for sugar, not the 4.0 used for carbohydrate generally).
#
# The code keeps the `manual:` prefix the plan assigned it and the recipe
# document references, but the data is entirely USDA, so `source` says so.
# ---------------------------------------------------------------------------
SUGAR = ManualIngredient(
    code="manual:sugar",
    name="Sugar, white, granulated",
    source="USDA",
    food_group="Sugars",
    diet_tags=VEG_TAGS,
    nutrients=(
        NutrientValue("energy", 387.0, "kcal", SR_LEGACY),
        NutrientValue("protein", 0.0, "g", SR_LEGACY),
        NutrientValue("fat", 0.0, "g", SR_LEGACY),
        NutrientValue("saturated_fat", 0.0, "g", SR_LEGACY),
        NutrientValue("carbohydrate", 99.98, "g", SR_LEGACY),
        # Every gram of it is a free sugar by definition -- this is the
        # canonical case the free_sugar nutrient exists to catch.
        NutrientValue("free_sugar", 99.8, "g", SR_LEGACY),
        NutrientValue("fibre", 0.0, "g", SR_LEGACY),
        NutrientValue("cholesterol", 0.0, "mg", SR_LEGACY),
        NutrientValue("calcium", 1.0, "mg", SR_LEGACY),
        NutrientValue("phosphorus", 0.0, "mg", SR_LEGACY),
        NutrientValue("magnesium", 0.0, "mg", SR_LEGACY),
        NutrientValue("iron", 0.05, "mg", SR_LEGACY),
        NutrientValue("zinc", 0.01, "mg", SR_LEGACY),
        NutrientValue("selenium", 0.6, "ug", SR_LEGACY),
        NutrientValue("copper", 0.007, "mg", SR_LEGACY),
        NutrientValue("manganese", 0.004, "mg", SR_LEGACY),
        NutrientValue("potassium", 2.0, "mg", SR_LEGACY),
        NutrientValue("sodium", 1.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_a", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_d", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_e", 0.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_k", 0.0, "ug", SR_LEGACY),
        NutrientValue("thiamine", 0.0, "mg", SR_LEGACY),
        NutrientValue("riboflavin", 0.019, "mg", SR_LEGACY),
        NutrientValue("niacin", 0.0, "mg", SR_LEGACY),
        NutrientValue("pantothenic_acid", 0.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_b6", 0.0, "mg", SR_LEGACY),
        NutrientValue("folate", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_b12", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_c", 0.0, "mg", SR_LEGACY),
        # iodine, biotin: not reported for sugar. Left NULL.
    ),
)


# ---------------------------------------------------------------------------
# 4. usda:coffee_brewed -- brewed coffee, PER 100 g OF LIQUID
#
# USDA SR Legacy fdc_id 171890, "Beverages, coffee, brewed, prepared with tap
# water" (NDB 14209), retrieved 2026-08-16. Not in the Foundation release.
#
# Why this ingredient exists at all: the recipe model computes nutrients from
# raw ingredient mass, so listing "24 g coffee powder" in filter coffee credits
# the cup with the full composition of 24 g of ground coffee -- the protein,
# fat, fibre, magnesium and potassium of beans that are steeped and thrown
# away. Only the water-soluble extractives reach the tumbler. Pricing the drink
# by the weight of the LIQUID fixes that at source, which is why these two rows
# are ingredients rather than a fudge factor on the powder.
#
# Strength caveat, stated so it is not invisible: this row is US drip strength
# (99.4 g water, 40 mg caffeine per 100 g). South Indian filter decoction is
# roughly three times stronger before it is cut with milk. Recipes list the
# decoction at its literal liquid weight, so the coffee-derived micronutrients
# -- potassium 49 mg, riboflavin 0.076 mg, pantothenic acid 0.254 mg per 100 g
# -- are understated by about that factor. The absolute amounts are small
# (~50 mg potassium per tumbler) and energy, fat and protein are unaffected
# because brewed coffee is 99% water; the milk and sugar dominate every number
# the app acts on.
# ---------------------------------------------------------------------------
COFFEE_BREWED = ManualIngredient(
    code="usda:coffee_brewed",
    name="Coffee, brewed, prepared with tap water",
    source="USDA",
    food_group="Beverages",
    diet_tags=VEG_TAGS,
    nutrients=(
        NutrientValue("energy", 1.0, "kcal", SR_LEGACY),
        NutrientValue("protein", 0.12, "g", SR_LEGACY),
        NutrientValue("fat", 0.02, "g", SR_LEGACY),
        NutrientValue("saturated_fat", 0.002, "g", SR_LEGACY),
        NutrientValue("carbohydrate", 0.0, "g", SR_LEGACY),
        NutrientValue("fibre", 0.0, "g", SR_LEGACY),
        NutrientValue("cholesterol", 0.0, "mg", SR_LEGACY),
        NutrientValue("calcium", 2.0, "mg", SR_LEGACY),
        NutrientValue("phosphorus", 3.0, "mg", SR_LEGACY),
        NutrientValue("magnesium", 3.0, "mg", SR_LEGACY),
        NutrientValue("iron", 0.01, "mg", SR_LEGACY),
        NutrientValue("zinc", 0.02, "mg", SR_LEGACY),
        NutrientValue("selenium", 0.0, "ug", SR_LEGACY),
        NutrientValue("copper", 0.002, "mg", SR_LEGACY),
        NutrientValue("manganese", 0.023, "mg", SR_LEGACY),
        NutrientValue("potassium", 49.0, "mg", SR_LEGACY),
        NutrientValue("sodium", 2.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_a", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_d", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_e", 0.01, "mg", SR_LEGACY),
        NutrientValue("vitamin_k", 0.1, "ug", SR_LEGACY),
        NutrientValue("thiamine", 0.014, "mg", SR_LEGACY),
        NutrientValue("riboflavin", 0.076, "mg", SR_LEGACY),
        NutrientValue("niacin", 0.191, "mg", SR_LEGACY),
        NutrientValue("pantothenic_acid", 0.254, "mg", SR_LEGACY),
        NutrientValue("vitamin_b6", 0.001, "mg", SR_LEGACY),
        NutrientValue("folate", 2.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_b12", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_c", 0.0, "mg", SR_LEGACY),
        # Black coffee carries no sugar of its own; what the app should count
        # is the sugar the recipe adds, which is a separate ingredient.
        NutrientValue("free_sugar", 0.0, "g", NO_SUGAR_BEVERAGE),
        # iodine, biotin: not reported. Left NULL.
    ),
)


# ---------------------------------------------------------------------------
# 5. usda:tea_brewed -- brewed black tea, PER 100 g OF LIQUID
#
# USDA SR Legacy fdc_id 173227, "Beverages, tea, black, brewed, prepared with
# tap water" (NDB 14355), retrieved 2026-08-16. Not in the Foundation release.
# Same infusion argument as coffee above: tea leaves are steeped and discarded,
# so the drink is priced by liquid weight, not leaf weight.
#
# Note the manganese: 0.219 mg per 100 g is nearly ten times brewed coffee's,
# and tea is a genuinely significant manganese source for a daily tea drinker.
# That only shows up because the drink is modelled as liquid.
# ---------------------------------------------------------------------------
TEA_BREWED = ManualIngredient(
    code="usda:tea_brewed",
    name="Tea, black, brewed, prepared with tap water",
    source="USDA",
    food_group="Beverages",
    diet_tags=VEG_TAGS,
    nutrients=(
        NutrientValue("energy", 1.0, "kcal", SR_LEGACY),
        NutrientValue("protein", 0.0, "g", SR_LEGACY),
        NutrientValue("fat", 0.0, "g", SR_LEGACY),
        NutrientValue("saturated_fat", 0.002, "g", SR_LEGACY),
        NutrientValue("carbohydrate", 0.3, "g", SR_LEGACY),
        NutrientValue("fibre", 0.0, "g", SR_LEGACY),
        NutrientValue("cholesterol", 0.0, "mg", SR_LEGACY),
        NutrientValue("calcium", 0.0, "mg", SR_LEGACY),
        NutrientValue("phosphorus", 1.0, "mg", SR_LEGACY),
        NutrientValue("magnesium", 3.0, "mg", SR_LEGACY),
        NutrientValue("iron", 0.02, "mg", SR_LEGACY),
        NutrientValue("zinc", 0.02, "mg", SR_LEGACY),
        NutrientValue("selenium", 0.0, "ug", SR_LEGACY),
        NutrientValue("copper", 0.01, "mg", SR_LEGACY),
        NutrientValue("manganese", 0.219, "mg", SR_LEGACY),
        NutrientValue("potassium", 37.0, "mg", SR_LEGACY),
        NutrientValue("sodium", 3.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_a", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_d", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_e", 0.0, "mg", SR_LEGACY),
        NutrientValue("vitamin_k", 0.0, "ug", SR_LEGACY),
        NutrientValue("thiamine", 0.0, "mg", SR_LEGACY),
        NutrientValue("riboflavin", 0.014, "mg", SR_LEGACY),
        NutrientValue("niacin", 0.0, "mg", SR_LEGACY),
        NutrientValue("pantothenic_acid", 0.011, "mg", SR_LEGACY),
        NutrientValue("vitamin_b6", 0.0, "mg", SR_LEGACY),
        NutrientValue("folate", 5.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_b12", 0.0, "ug", SR_LEGACY),
        NutrientValue("vitamin_c", 0.0, "mg", SR_LEGACY),
        NutrientValue("free_sugar", 0.0, "g", NO_SUGAR_BEVERAGE),
        # iodine, biotin: not reported. Left NULL.
    ),
)


MANUAL_INGREDIENTS: list[ManualIngredient] = [SALT, CURD, SUGAR, COFFEE_BREWED, TEA_BREWED]


def seed_manual_ingredients(db: Session) -> int:
    """Insert or update the five non-IFCT ingredients. Safe to re-run.

    Requires seed_nutrients() to have run: a nutrient code with no Nutrient row
    is skipped rather than guessed at, the same way load_ifct handles it.
    """
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    existing = {i.code: i for i in db.scalars(select(Ingredient))}

    for spec in MANUAL_INGREDIENTS:
        ingredient = existing.get(spec.code)
        if ingredient is None:
            ingredient = Ingredient(code=spec.code, source=spec.source)
            db.add(ingredient)

        ingredient.name = spec.name
        ingredient.source = spec.source
        ingredient.food_group = spec.food_group
        ingredient.diet_tags = spec.diet_tags
        db.flush()

        for value in spec.nutrients:
            nutrient = nutrients.get(value.code)
            if nutrient is None:
                continue

            # Every unit conversion goes through the one shared helper, so an
            # ug/mg slip here would have to be a slip everywhere.
            per_100g = to_canonical(value.value, value.unit, nutrient.unit)

            row = db.scalar(
                select(IngredientNutrient).where(
                    IngredientNutrient.ingredient_id == ingredient.id,
                    IngredientNutrient.nutrient_id == nutrient.id,
                )
            )
            if row is None:
                db.add(
                    IngredientNutrient(
                        ingredient_id=ingredient.id,
                        nutrient_id=nutrient.id,
                        per_100g=per_100g,
                        source=value.source,
                    )
                )
            else:
                row.per_100g = per_100g
                row.source = value.source

    db.flush()
    return len(MANUAL_INGREDIENTS)
