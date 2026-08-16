"""72 authored South Indian dishes, as raw ingredients with gram weights.

The human-readable version of this file, with the reasoning behind every
proportion, is docs/superpowers/specs/2026-08-16-seed-recipes.md. The two must
stay in step: that document is the record a cook can check, this is what the app
computes from. Every number here was reviewed by someone who eats this food.

Reading the data
----------------
Ingredient weights are RAW and DRY, for one batch. Water added during cooking is
not an ingredient -- it enters the model only through `yield_factor`:

    yield_factor = cooked batch weight / sum of the raw ingredient grams

On that dry basis a plain dosa is 1.70, not below 1.0: 400 g of dry rice becomes
roughly a kilo of dosas. Only genuinely dry-fried or crisped things sit under
1.0 -- rava dosa 0.95, poriyal 0.75-0.88, murukku 0.95, bajji and bonda 0.90,
fish fry 0.80, omelette 0.85. Rasam sits at 3.3-5.75 because it is mostly the
water you added.

Volume-to-weight conversions used to turn published recipes into grams
(240 ml cup): raw/parboiled rice 200 g, urad dal 190 g, toor/channa dal 200 g,
rava 170 g, grated fresh coconut 80 g, milk/curd 240 g, sugar 200 g (1 tsp 4 g),
jaggery 180 g, oil/ghee 14 g per tbsp and 4.5 g per tsp, whole spices 3-4 g per
tsp, salt 6 g per tsp.

`serves` is the number of DEFAULT-measure portions in one batch, so
`measures[0][1] * serves` reconstructs the cooked batch weight. For the three
store-cupboard powders that means a large number (a batch of sambar powder is
about 140 teaspoons); a spice tin is not eaten in meals, and pretending
otherwise would put a fictional number in front of the user.

Decisions baked into this data
------------------------------
* Idli/dosa batter is 4:1 rice to urad dal BY VOLUME -- 400 g rice to 95 g dal
  by weight, not the 3:1 (400:125) first drafted. This is eaten daily, so a 30%
  overstatement of the dal would inflate protein in every logged breakfast.
* Sweets and ghee use the everyday home version, not the festival ratio. These
  get logged as ordinary meals; an inflated default silently overstates calories
  every single time. See kesari, sakkarai pongal and ven pongal below.
* Fish is a VARIANT SET, not one hardcoded species -- see the fish section.
* Coffee and tea are built from brewed LIQUID, not dry grounds. Listing 24 g of
  coffee powder would credit the cup with the full composition of beans that are
  steeped and thrown away. See the drinks section.
* Composite condiments are INLINED. `Recipe.ingredients` references ingredients,
  not other dishes, so sambar lists coriander seed and red chilli directly
  instead of "12 g sambar powder". Sambar powder also exists as its own dish for
  when you log a spoonful, so those spice rows appear twice on purpose.
* Deep-fried items list only the oil ABSORBED BY THE FOOD, not the oil in the
  kadai, and each fried recipe states its retention percentage in a comment.
  Published figures for Indian fried snacks range from 8% to 25%, so this is the
  document's largest single error source; keeping the percentage visible is what
  makes it revisable.

Proxy substitutions, where IFCT has no row for the exact form used
-----------------------------------------------------------------
rice flour -> ifct:A015 (rice flour IS milled raw rice); besan and roasted gram
(pottukadalai) -> ifct:B001 Bengal gram dal; urad flour -> ifct:B003; coconut
milk -> ifct:H007 fresh kernel, which is how it is extracted at home and which
overstates fibre because the squeezed residue is really discarded. Cinnamon, bay
leaf, fennel, star anise, sago and cooking soda have no IFCT row at all and are
omitted; all are sub-gram except the soda, which means bajji and bonda sodium is
slightly understated.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    code: str
    name: str
    slot_tags: str  # space separated: breakfast lunch snack dinner
    diet_tags: str  # vegetarian | eggetarian | fishetarian | nonveg
    yield_factor: float  # cooked weight / raw weight
    serves: int
    measures: list[tuple[str, float]]  # ("1 idli", 45.0); the first is the default
    ingredients: list[tuple[str, float]]  # (ingredient code, raw grams per batch)


VEG = "vegetarian"

# The one batter, shared by idli, dosa, masala dosa and uttapam: 4:1 parboiled
# rice to urad dal by volume = 400 g : 95 g by weight, plus a little fenugreek
# for the ferment. Scaled proportionally where a dish uses part of a batch.
BATTER_RICE_TO_DAL = 400 / 95


# ---------------------------------------------------------------------------
# 1. Tiffin / breakfast items
# ---------------------------------------------------------------------------
_TIFFIN: list[Recipe] = [
    Recipe(
        code="si:idli",
        name="Idli",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # Dry grain is soaked, ground with water and steamed, so the cooked
        # weight is far above the raw: 510 g raw -> ~1326 g, about 29 idlis.
        yield_factor=2.60,
        serves=29,
        measures=[("1 idli", 45.0), ("2 idli", 90.0), ("3 idli", 135.0)],
        ingredients=[
            ("ifct:A014", 400.0),  # Rice, parboiled, milled
            ("ifct:B003", 95.0),  # Black gram dal (urad) -- 4:1 by volume
            ("ifct:G026", 5.0),  # Fenugreek seeds
            ("manual:salt", 10.0),
        ],
    ),
    Recipe(
        code="si:dosa_plain",
        name="Plain dosa",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # Same batter ground thinner. Lower than idli because a thin batter
        # loses water on the griddle. 542 g raw -> ~921 g, about 15 dosas.
        yield_factor=1.70,
        serves=15,
        measures=[("1 dosa", 60.0), ("2 dosa", 120.0)],
        ingredients=[
            ("ifct:A014", 400.0),
            ("ifct:B003", 95.0),
            ("ifct:G026", 5.0),
            ("manual:salt", 10.0),
            ("ifct:T004", 32.0),  # Gingelly oil, ~2 g smeared per dosa
        ],
    ),
    Recipe(
        code="si:dosa_masala",
        name="Masala dosa",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # Yield 1.00: the potato masala dominates and potato neither gains nor
        # loses much weight, cancelling the batter's water gain.
        yield_factor=1.00,
        serves=8,
        measures=[("1 masala dosa", 160.0)],  # ~60 g dosa + ~100 g potato masala
        ingredients=[
            ("ifct:A014", 270.0),  # two-thirds of a batter batch...
            ("ifct:B003", 64.0),  # ...at the same 4:1 ratio
            ("ifct:G026", 4.0),
            ("ifct:F006", 600.0),  # Potato
            ("ifct:G017", 200.0),  # Onion, big
            ("ifct:T012", 50.0),  # Sunflower oil
            ("manual:salt", 14.0),
            ("ifct:G001", 12.0),  # Green chilli
            ("ifct:B001", 10.0),  # Bengal gram dal
            ("ifct:G009", 10.0),  # Coriander leaves
            ("ifct:G014", 8.0),  # Ginger
            ("ifct:H013", 4.0),  # Mustard seeds
            ("ifct:G010", 4.0),  # Curry leaves
            ("ifct:G033", 2.0),  # Turmeric
        ],
    ),
    Recipe(
        code="si:dosa_rava",
        name="Rava dosa",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # Standard 3:2:1 rava : rice flour : maida. Poured, not spread, and
        # cooked lace-thin, so it ends up lighter than its dry ingredients.
        yield_factor=0.95,
        serves=4,
        measures=[("2 rava dosa", 120.0), ("1 rava dosa", 60.0)],
        ingredients=[
            ("ifct:A022", 150.0),  # Wheat semolina (rava)
            ("ifct:A015", 100.0),  # Rice, raw, milled -- proxy for rice flour
            ("ifct:G017", 100.0),
            ("ifct:T012", 60.0),
            ("ifct:A018", 50.0),  # Refined wheat flour (maida)
            ("ifct:G001", 10.0),
            ("ifct:G014", 8.0),
            ("manual:salt", 8.0),
            ("ifct:G009", 8.0),
            ("ifct:G025", 4.0),  # Cumin
            ("ifct:G010", 4.0),
            ("ifct:G031", 3.0),  # Black pepper
        ],
    ),
    Recipe(
        code="si:adai",
        name="Adai",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # 1 cup rice to 1 cup mixed dals. Coarse-ground, thick and griddled --
        # absorbs less than idli, more than a thin dosa. Not the idli batter.
        yield_factor=1.25,
        serves=8,
        measures=[("1 adai", 95.0)],
        ingredients=[
            ("ifct:A014", 200.0),
            ("ifct:G017", 100.0),
            ("ifct:B021", 60.0),  # Red gram dal (toor)
            ("ifct:B001", 60.0),
            ("ifct:B003", 40.0),
            ("ifct:B010", 40.0),  # Green gram dal (moong)
            ("ifct:H007", 40.0),  # Fresh coconut
            ("ifct:T004", 40.0),
            ("ifct:G022", 12.0),  # Red chilli
            ("manual:salt", 10.0),
            ("ifct:G010", 5.0),
            ("ifct:G019", 1.0),  # Asafoetida
        ],
    ),
    Recipe(
        code="si:uttapam",
        name="Uttapam (onion-tomato)",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # Dosa batter poured thick with the topping pressed in: retains more
        # water than a dosa, less than a steamed idli.
        yield_factor=1.55,
        serves=6,
        measures=[("1 uttapam", 170.0)],
        ingredients=[
            ("ifct:A014", 300.0),  # three-quarters of a batter batch...
            ("ifct:B003", 71.0),  # ...at the same 4:1 ratio
            ("ifct:G017", 120.0),
            ("ifct:D075", 100.0),  # Tomato
            ("ifct:T012", 30.0),
            ("ifct:G001", 10.0),
            ("ifct:G009", 10.0),
            ("manual:salt", 8.0),
            ("ifct:G026", 4.0),
        ],
    ),
    Recipe(
        code="si:ven_pongal",
        name="Ven pongal",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # 3:1 rice to moong dal by volume, cooked soft with ~4 parts water.
        # GHEE: 30 g for 5, not the 45 g first drafted. 45 g is 9 g (2 tsp) of
        # ghee per serving, a temple/restaurant pongal; 30 g is 6 g per serving,
        # which is what a weekday morning actually gets. This dish is logged as
        # an ordinary breakfast, so the default has to be the ordinary version.
        yield_factor=2.60,
        serves=5,
        measures=[("1 cup", 220.0), ("1/2 cup", 110.0)],
        ingredients=[
            ("ifct:A015", 250.0),  # Rice, raw, milled
            ("ifct:B010", 85.0),
            ("ifct:T013", 30.0),  # Ghee
            ("ifct:H005", 25.0),  # Cashew nut
            ("ifct:G014", 12.0),
            ("manual:salt", 8.0),
            ("ifct:G031", 6.0),
            ("ifct:G025", 5.0),
            ("ifct:G010", 5.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:sakkarai_pongal",
        name="Sakkarai pongal",
        slot_tags="breakfast snack",
        diet_tags=VEG,
        # JAGGERY: 150 g for 6, not the 250 g first drafted. 250 g is jaggery
        # slightly exceeding the combined grain weight -- a festival prasadam
        # ratio. 150 g is the home version and takes ~65 kcal per serving off a
        # dish people log as breakfast.
        # Ghee stays at 60 g: this is a sweet, and halving the jaggery has
        # already taken the richness down a long way. Flagged rather than
        # silently changed.
        yield_factor=1.75,
        serves=6,
        measures=[("1 cup", 180.0), ("1/2 cup", 90.0)],
        ingredients=[
            ("ifct:I001", 150.0),  # Jaggery, cane
            ("ifct:A015", 200.0),
            ("ifct:L002", 100.0),  # Cow milk
            ("ifct:B010", 60.0),
            ("ifct:T013", 60.0),
            ("ifct:H005", 30.0),
            ("ifct:E057", 20.0),  # Raisins
            ("ifct:G020", 2.0),  # Cardamom
        ],
    ),
    Recipe(
        code="si:upma",
        name="Upma (rava)",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=1.95,  # rava to water 1:2.5 by volume; rava roughly triples
        serves=4,
        measures=[("1 cup", 185.0)],
        ingredients=[
            ("ifct:A022", 200.0),
            ("ifct:G017", 100.0),
            ("ifct:T012", 25.0),
            ("ifct:G001", 10.0),
            ("ifct:G014", 8.0),
            ("ifct:G009", 8.0),
            ("ifct:B001", 8.0),
            ("ifct:B003", 8.0),
            ("manual:salt", 6.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
        ],
    ),
    Recipe(
        code="si:semiya_upma",
        name="Semiya upma",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=1.70,  # roasted vermicelli to water 1:2; absorbs less than rava
        serves=4,
        measures=[("1 cup", 185.0)],
        ingredients=[
            ("ifct:A024", 200.0),  # Wheat vermicelli, roasted
            ("ifct:G017", 80.0),
            ("ifct:F002", 60.0),  # Carrot
            ("ifct:D061", 40.0),  # Peas, fresh
            ("ifct:T012", 22.0),
            ("ifct:G001", 10.0),
            ("manual:salt", 6.0),
            ("ifct:B003", 6.0),
            ("ifct:B001", 6.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
        ],
    ),
    Recipe(
        code="si:idiyappam",
        name="Idiyappam",
        slot_tags="breakfast dinner",
        diet_tags=VEG,
        yield_factor=2.35,  # flour kneaded with hot water and steamed: pure absorption
        serves=4,
        measures=[("3 idiyappam", 180.0), ("1 idiyappam", 60.0)],
        ingredients=[
            ("ifct:A015", 300.0),  # proxy for rice flour
            ("ifct:T001", 10.0),  # Coconut oil
            ("manual:salt", 5.0),
        ],
    ),
    Recipe(
        code="si:appam",
        name="Appam",
        slot_tags="breakfast dinner",
        diet_tags=VEG,
        # Lower than idiyappam because the appam cooks open-faced and its lacy
        # edge dries out.
        yield_factor=1.70,
        serves=5,
        measures=[("2 appam", 150.0), ("1 appam", 75.0)],
        ingredients=[
            ("ifct:A015", 300.0),
            ("ifct:H007", 100.0),
            ("manual:sugar", 15.0),
            ("ifct:T001", 15.0),
            ("manual:salt", 5.0),
        ],
    ),
    Recipe(
        code="si:puttu",
        name="Puttu",
        slot_tags="breakfast dinner",
        diet_tags=VEG,
        # Absorbs less than idiyappam: the flour is only damp, never a dough.
        yield_factor=1.90,
        serves=4,
        measures=[("1 puttu cylinder", 190.0)],
        ingredients=[
            ("ifct:A015", 300.0),  # proxy for puttu flour
            ("ifct:H007", 100.0),
            ("manual:salt", 5.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 2. Rice dishes
# ---------------------------------------------------------------------------
_RICE: list[Recipe] = [
    Recipe(
        code="si:rice_plain",
        name="Plain rice",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=2.90,  # standard absorption cooking: 1 g dry -> 2.9 g cooked
        serves=4,
        measures=[("1 cup", 200.0), ("1 ladle", 150.0)],
        ingredients=[("ifct:A015", 300.0)],
    ),
    Recipe(
        code="si:rice_parboiled",
        name="Plain rice, parboiled (puzhungal arisi)",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # Kept separate from raw milled rice because the everyday Tamil Nadu
        # rice is parboiled, and it takes marginally more water.
        yield_factor=3.00,
        serves=4,
        measures=[("1 cup", 210.0), ("1 ladle", 150.0)],
        ingredients=[("ifct:A014", 300.0)],
    ),
    Recipe(
        code="si:kanji",
        name="Kanji (rice gruel)",
        slot_tags="breakfast dinner",
        diet_tags=VEG,
        # Very high: it is mostly the cooking water, which is drunk not drained.
        yield_factor=6.00,
        serves=2,
        measures=[("1 bowl", 300.0)],
        ingredients=[("ifct:A014", 100.0), ("manual:salt", 3.0)],
    ),
    Recipe(
        code="si:curd_rice",
        name="Curd rice (thayir sadam)",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # Modest yield: curd and milk are already wet, so only the rice swells.
        yield_factor=1.50,
        serves=4,
        measures=[("1 cup", 280.0)],
        ingredients=[
            ("usda:curd", 400.0),
            ("ifct:A015", 200.0),
            ("ifct:L002", 100.0),
            ("ifct:T012", 10.0),
            ("ifct:G001", 8.0),
            ("ifct:G014", 8.0),
            ("ifct:G009", 6.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 3.0),
            ("ifct:G010", 3.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:lemon_rice",
        name="Lemon rice",
        slot_tags="lunch snack dinner",
        diet_tags=VEG,
        yield_factor=2.10,
        serves=4,
        measures=[("1 cup", 220.0)],
        ingredients=[
            ("ifct:A015", 250.0),
            ("ifct:E033", 45.0),  # Lemon juice, about two limes
            ("ifct:T004", 35.0),
            ("ifct:H012", 25.0),  # Ground nut
            ("ifct:B001", 12.0),
            ("ifct:B003", 10.0),
            ("ifct:G001", 8.0),
            ("ifct:G022", 6.0),
            ("manual:salt", 6.0),
            ("ifct:G009", 6.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:tamarind_rice",
        name="Tamarind rice (puliyodharai)",
        slot_tags="lunch snack",
        diet_tags=VEG,
        yield_factor=2.00,
        serves=5,
        measures=[("1 cup", 210.0)],
        ingredients=[
            ("ifct:A015", 300.0),
            ("ifct:E064", 60.0),  # Tamarind, pulp -- IFCT DOES have this
            # Gingelly oil deliberately high: puliyodharai is an oil-preserved
            # dish and this is not a place to under-report.
            ("ifct:T004", 60.0),
            ("ifct:H012", 30.0),
            ("ifct:B001", 15.0),
            ("ifct:B003", 12.0),
            ("ifct:G022", 10.0),
            ("manual:salt", 10.0),
            ("ifct:I001", 10.0),
            ("ifct:G024", 6.0),  # Coriander seeds
            ("ifct:G010", 6.0),
            ("ifct:H013", 5.0),
            ("ifct:G026", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:coconut_rice",
        name="Coconut rice (thengai sadam)",
        slot_tags="lunch snack",
        diet_tags=VEG,
        yield_factor=1.95,
        serves=4,
        measures=[("1 cup", 230.0)],
        ingredients=[
            ("ifct:A015", 250.0),
            ("ifct:H007", 120.0),  # roughly half a coconut, grated
            ("ifct:T001", 30.0),
            ("ifct:H005", 20.0),
            ("ifct:B003", 12.0),
            ("ifct:B001", 12.0),
            ("ifct:G001", 8.0),
            ("ifct:G022", 6.0),
            ("manual:salt", 6.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 3. Kuzhambu, sambar and rasam
#
# The largest yield factors in the set, because these are mostly added water.
# The absolute nutrients come from the dal, oil and tamarind; the yield factor
# only spreads them over the final volume. The three rasam figures (tomato 3.30,
# pepper 5.75, lemon 4.45) were reviewed and kept as drafted -- rasam really is
# a drinkable consistency, and a thicker pot would raise every per-cup number.
# ---------------------------------------------------------------------------
_KUZHAMBU: list[Recipe] = [
    Recipe(
        code="si:sambar",
        name="Sambar",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # ~1.2 L of water in, some boiled off. Spices listed inline rather than
        # as "sambar powder" -- see the module docstring.
        yield_factor=2.15,
        serves=7,
        measures=[("1 cup", 200.0), ("1 ladle", 100.0)],
        ingredients=[
            ("ifct:B021", 150.0),
            ("ifct:D046", 100.0),  # Drumstick
            ("ifct:G018", 100.0),  # Onion, small (shallot)
            ("ifct:D075", 100.0),
            ("ifct:D031", 80.0),  # Brinjal
            ("ifct:F002", 60.0),
            ("ifct:E064", 30.0),
            ("ifct:T004", 20.0),
            ("ifct:G024", 12.0),
            ("ifct:G022", 10.0),
            ("manual:salt", 10.0),
            ("ifct:G009", 8.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:B001", 4.0),
            ("ifct:G025", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G026", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:rasam_tomato",
        name="Tomato rasam",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=3.30,
        serves=6,
        measures=[("1 cup", 200.0), ("1 ladle", 100.0)],
        ingredients=[
            ("ifct:D075", 250.0),
            ("ifct:B021", 30.0),
            ("ifct:E064", 20.0),
            ("ifct:G009", 10.0),
            ("ifct:T013", 10.0),
            ("ifct:G011", 8.0),  # Garlic, big cloves
            ("manual:salt", 8.0),
            ("ifct:G025", 5.0),
            ("ifct:G010", 5.0),
            ("ifct:G024", 5.0),
            ("ifct:G031", 4.0),
            ("ifct:G022", 4.0),
            ("ifct:H013", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:rasam_pepper",
        name="Pepper rasam (milagu rasam)",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # The medicinal version: heavy on pepper and cumin, very little solid
        # matter. 5.75 is the highest factor in the set and is entirely water.
        yield_factor=5.75,
        serves=6,
        measures=[("1 cup", 180.0)],
        ingredients=[
            ("ifct:D075", 80.0),
            ("ifct:E064", 25.0),
            ("ifct:B021", 25.0),
            ("ifct:G011", 10.0),
            ("ifct:T013", 10.0),
            ("ifct:G031", 8.0),
            ("ifct:G009", 8.0),
            ("manual:salt", 8.0),
            ("ifct:G025", 6.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:rasam_lemon",
        name="Lemon rasam",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=4.45,  # no tamarind; juice of two limes added off the heat
        serves=6,
        measures=[("1 cup", 180.0)],
        ingredients=[
            ("ifct:D075", 100.0),
            ("ifct:E033", 45.0),
            ("ifct:B021", 40.0),
            ("ifct:G001", 10.0),
            ("ifct:G009", 10.0),
            ("ifct:G014", 8.0),
            ("manual:salt", 8.0),
            ("ifct:T013", 8.0),
            ("ifct:G010", 5.0),
            ("ifct:G025", 4.0),
            ("ifct:G031", 3.0),
            ("ifct:H013", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:more_kuzhambu",
        name="More kuzhambu",
        slot_tags="lunch",
        diet_tags=VEG,
        # Low yield because curd IS the liquid -- little extra water goes in.
        yield_factor=1.30,
        serves=6,
        measures=[("1 cup", 195.0)],
        ingredients=[
            ("usda:curd", 500.0),
            ("ifct:D001", 250.0),  # Ash gourd
            ("ifct:H007", 60.0),
            ("ifct:B021", 20.0),
            ("ifct:T001", 15.0),
            ("ifct:G001", 12.0),
            ("ifct:B001", 10.0),
            ("manual:salt", 8.0),
            ("ifct:G014", 6.0),
            ("ifct:G025", 5.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G033", 2.0),
            ("ifct:G026", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:vatha_kuzhambu",
        name="Vatha kuzhambu (vengaya)",
        slot_tags="lunch",
        diet_tags=VEG,
        # The small-onion version: the sun-dried vathal (sundakkai,
        # manathakkali) that names the dish has no IFCT row. Tamarind-forward
        # and reduced thick, so the default measure is a deliberately small
        # 80 g ladle, not a full cup.
        yield_factor=2.15,
        serves=12,
        measures=[("1 ladle", 80.0), ("1 cup", 160.0)],
        ingredients=[
            ("ifct:G018", 150.0),
            ("ifct:D046", 80.0),
            ("ifct:E064", 60.0),
            ("ifct:T004", 60.0),
            ("ifct:G011", 15.0),
            ("ifct:G024", 12.0),
            ("ifct:G022", 12.0),
            ("ifct:B021", 10.0),
            ("ifct:I001", 10.0),
            ("manual:salt", 10.0),
            ("ifct:G010", 6.0),
            ("ifct:H013", 5.0),
            ("ifct:G026", 4.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 2.0),
        ],
    ),
    Recipe(
        code="si:kara_kuzhambu",
        name="Kara kuzhambu",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=2.00,  # less reduced than vatha kuzhambu
        serves=6,
        measures=[("1 cup", 200.0)],
        ingredients=[
            ("ifct:D031", 150.0),
            ("ifct:G018", 120.0),
            ("ifct:D046", 80.0),
            ("ifct:D075", 80.0),
            ("ifct:E064", 50.0),
            ("ifct:T004", 45.0),
            ("ifct:H007", 40.0),  # proxy for the ground coconut milk
            ("ifct:G011", 15.0),
            ("ifct:G024", 12.0),
            ("ifct:G022", 10.0),
            ("manual:salt", 10.0),
            ("ifct:G010", 6.0),
            ("ifct:H013", 5.0),
            ("ifct:G026", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 4. Vegetable sides
#
# The dry sautes are where water genuinely leaves the food, so these sit below
# 1.0 -- cabbage collapses hardest (0.75), carrot least (0.88).
# ---------------------------------------------------------------------------
_VEGETABLES: list[Recipe] = [
    Recipe(
        code="si:poriyal_beans",
        name="Beans poriyal",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=0.85,
        serves=4,
        measures=[("1 serving", 110.0), ("1 cup", 130.0)],
        ingredients=[
            ("ifct:D050", 400.0),  # French beans
            ("ifct:H007", 50.0),
            ("ifct:T001", 18.0),
            ("ifct:B001", 8.0),
            ("ifct:B003", 8.0),
            ("ifct:G001", 6.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G022", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:poriyal_cabbage",
        name="Cabbage poriyal",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=0.75,  # cabbage is ~92% water and collapses
        serves=4,
        measures=[("1 serving", 105.0)],
        ingredients=[
            ("ifct:C015", 450.0),
            ("ifct:H007", 50.0),
            ("ifct:T001", 16.0),
            ("ifct:B001", 8.0),
            ("ifct:B003", 8.0),
            ("ifct:G001", 8.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:poriyal_carrot",
        name="Carrot poriyal",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=0.88,
        serves=4,
        measures=[("1 serving", 110.0)],
        ingredients=[
            ("ifct:F002", 400.0),
            ("ifct:H007", 50.0),
            ("ifct:T001", 16.0),
            ("ifct:B001", 8.0),
            ("ifct:B003", 8.0),
            ("ifct:G001", 6.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
        ],
    ),
    Recipe(
        code="si:kootu",
        name="Kootu (bottle gourd, poricha)",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # Above 1.0 because the dal absorbs water even though the gourd sheds it.
        yield_factor=1.60,
        serves=5,
        measures=[("1 cup", 195.0)],
        ingredients=[
            ("ifct:D007", 400.0),  # Bottle gourd
            ("ifct:B010", 100.0),
            ("ifct:H007", 60.0),
            ("ifct:T001", 15.0),
            ("ifct:G001", 8.0),
            ("manual:salt", 6.0),
            ("ifct:B003", 6.0),
            ("ifct:G025", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G031", 3.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:avial",
        name="Avial",
        slot_tags="lunch",
        diet_tags=VEG,
        # The curd-soured Tamil Nadu version. The Kerala version uses raw mango
        # or tamarind and no curd, which changes the calcium contribution.
        yield_factor=1.15,
        serves=6,
        measures=[("1 cup", 180.0)],
        ingredients=[
            ("usda:curd", 150.0),
            ("ifct:H007", 120.0),
            ("ifct:D046", 100.0),
            ("ifct:D063", 100.0),  # Plantain, green
            ("ifct:D038", 100.0),  # Cho-cho-marrow (chow chow)
            ("ifct:F017", 100.0),  # Yam, elephant
            ("ifct:F002", 80.0),
            ("ifct:D065", 80.0),  # Pumpkin
            ("ifct:D032", 60.0),  # Broad beans
            ("ifct:T001", 25.0),  # raw coconut oil, added off the heat
            ("ifct:G001", 15.0),
            ("manual:salt", 8.0),
            ("ifct:G025", 6.0),
            ("ifct:G010", 5.0),
            ("ifct:G033", 2.0),
        ],
    ),
    Recipe(
        code="si:thoran",
        name="Cabbage thoran",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # The one deliberate Kerala dish in the set: more coconut, crushed
        # garlic and cumin, no dal tempering.
        yield_factor=0.80,
        serves=4,
        measures=[("1 serving", 115.0)],
        ingredients=[
            ("ifct:C015", 400.0),
            ("ifct:H007", 80.0),
            ("ifct:G018", 40.0),
            ("ifct:T001", 18.0),
            ("ifct:G001", 10.0),
            ("ifct:G012", 6.0),  # Garlic, small cloves
            ("manual:salt", 5.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G025", 3.0),
            ("ifct:G033", 2.0),
        ],
    ),
    Recipe(
        code="si:keerai_masiyal",
        name="Keerai masiyal",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # Greens collapse to about a third, but the dal swells and the cooking
        # water is kept in -- net 1.10.
        yield_factor=1.10,
        serves=4,
        measures=[("1 serving", 150.0)],
        ingredients=[
            ("ifct:C002", 400.0),  # Amaranth leaves
            ("ifct:B010", 60.0),
            ("ifct:G018", 40.0),
            ("ifct:T004", 12.0),
            ("ifct:G011", 10.0),
            ("ifct:G022", 5.0),
            ("manual:salt", 5.0),
            ("ifct:G025", 4.0),
            ("ifct:H013", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:kurma",
        name="Vegetable kurma",
        slot_tags="breakfast lunch dinner",
        diet_tags=VEG,
        # The standard accompaniment to idiyappam, appam and parotta. Cinnamon,
        # bay leaf and fennel have no IFCT row and are omitted.
        yield_factor=1.25,
        serves=5,
        measures=[("1 cup", 230.0)],
        ingredients=[
            ("ifct:F006", 200.0),
            ("ifct:F002", 120.0),
            ("ifct:G017", 120.0),
            ("ifct:D050", 100.0),
            ("ifct:D075", 100.0),
            ("ifct:D061", 80.0),
            ("ifct:H007", 80.0),
            ("ifct:T012", 35.0),
            ("ifct:H005", 15.0),
            ("ifct:G011", 12.0),
            ("ifct:G001", 12.0),
            ("ifct:G014", 10.0),
            ("ifct:G016", 10.0),  # Mint leaves
            ("ifct:G009", 10.0),
            ("manual:salt", 8.0),
            ("ifct:G032", 6.0),  # Poppy seeds
            ("ifct:G033", 2.0),
            ("ifct:G020", 2.0),
            ("ifct:G023", 1.0),  # Cloves
        ],
    ),
    Recipe(
        code="si:sundal_chana",
        name="Chana sundal",
        slot_tags="snack",
        diet_tags=VEG,
        # Dried whole Bengal gram soaked overnight and boiled -- roughly 2.5x
        # its dry weight -- then tossed with coconut and a tempering.
        yield_factor=1.95,
        serves=5,
        measures=[("1 cup", 120.0)],
        ingredients=[
            ("ifct:B002", 200.0),  # Bengal gram, whole
            ("ifct:H007", 60.0),
            ("ifct:T001", 12.0),
            ("ifct:B003", 6.0),
            ("ifct:G001", 6.0),
            ("ifct:G022", 5.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:sundal_pattani",
        name="Pattani sundal",
        slot_tags="snack",
        diet_tags=VEG,
        yield_factor=1.95,
        serves=5,
        measures=[("1 cup", 120.0)],
        ingredients=[
            ("ifct:B017", 200.0),  # Peas, dry
            ("ifct:H007", 60.0),
            ("ifct:T001", 12.0),
            ("ifct:B003", 6.0),
            ("ifct:G001", 6.0),
            ("ifct:G022", 5.0),
            ("manual:salt", 5.0),
            ("ifct:G014", 5.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G019", 1.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 5. Non-vegetarian
#
# FISH IS A VARIANT SET, NOT ONE SPECIES. The user picks the fish when logging,
# and the planner has to be able to offer the fish that was actually bought.
# IFCT's 91 marine fish are not interchangeable: per 100 g raw, anchovy carries
# 0.78 g fat and sardine 8.99 g, an eleven-fold spread that moves the calorie
# and omega-3 numbers for the whole meal. Hardcoding one species would make
# every fish log wrong for anyone who eats a different one.
#
# The four species, chosen as what a Tamil Nadu household actually buys:
#   ifct:P087 Vanjaram  (seer / Spanish mackerel) -- the prestige kuzhambu fish
#   ifct:P071 Sardine   (mathi)                   -- the everyday cheap fish
#   ifct:P034 Mackerel  (ayila)                   -- the other everyday staple
#   ifct:P003 Anchovy   (nethili)                 -- small fry, fried whole
# They also happen to span the fat range end to end, which is exactly what makes
# the choice worth offering rather than averaging away.
#
# Non-fish ingredients are IDENTICAL across the variants of a dish; only the
# fish code differs. The shared name prefix is what groups them in a picker.
# ---------------------------------------------------------------------------
FISH_VARIANTS: list[tuple[str, str, str]] = [
    # (code suffix, ifct code, display suffix)
    ("vanjaram", "ifct:P087", "vanjaram / seer"),
    ("sardine", "ifct:P071", "sardine / mathi"),
    ("mackerel", "ifct:P034", "mackerel / ayila"),
    ("nethili", "ifct:P003", "nethili / anchovy"),
]

_FISH_KUZHAMBU_BASE: list[tuple[str, float]] = [
    ("ifct:G018", 100.0),
    ("ifct:D075", 100.0),
    ("ifct:E064", 50.0),  # tamarind-heavy, no coconut -- the Tamil Nadu style
    ("ifct:T004", 45.0),
    ("ifct:G024", 15.0),
    ("ifct:G011", 15.0),
    ("ifct:G022", 12.0),
    ("manual:salt", 10.0),
    ("ifct:G010", 5.0),
    ("ifct:H013", 4.0),
    ("ifct:G026", 3.0),
    ("ifct:G033", 3.0),
    ("ifct:G019", 1.0),
]

_FISH_FRY_BASE: list[tuple[str, float]] = [
    # DEEP-FRY OIL RETENTION: 40 g of the 396 g finished weight is absorbed
    # groundnut oil, i.e. 10%. Shallow-fried fish is the lowest retention in the
    # set because the masala coat is thin and the fish sheds water fast.
    # Published figures for Indian frying run 8-25%; revise here if measured.
    ("ifct:T005", 40.0),
    ("ifct:A015", 20.0),  # proxy for the rice flour coating
    ("ifct:G011", 10.0),
    ("ifct:G022", 8.0),
    ("ifct:G014", 8.0),
    ("manual:salt", 6.0),
    ("ifct:G033", 3.0),
]

_FISH: list[Recipe] = [
    Recipe(
        code=f"si:fish_kuzhambu_{suffix}",
        name=f"Fish kuzhambu ({display})",
        slot_tags="lunch dinner",
        diet_tags="fishetarian",
        yield_factor=1.50,
        serves=5,
        measures=[("1 serving", 260.0), ("1 ladle gravy", 100.0)],
        ingredients=[(fish_code, 500.0), *_FISH_KUZHAMBU_BASE],
    )
    for suffix, fish_code, display in FISH_VARIANTS
] + [
    Recipe(
        code=f"si:fish_fry_{suffix}",
        name=f"Fish fry ({display})",
        slot_tags="lunch dinner",
        diet_tags="fishetarian",
        # Sub-1.0: frying drives off water faster than the fish takes up oil.
        yield_factor=0.80,
        serves=4,
        measures=[("1 piece", 100.0)],
        ingredients=[(fish_code, 400.0), *_FISH_FRY_BASE],
    )
    for suffix, fish_code, display in FISH_VARIANTS
]

_OTHER_NONVEG: list[Recipe] = [
    Recipe(
        code="si:chicken_curry",
        name="Chicken curry",
        slot_tags="lunch dinner",
        diet_tags="nonveg",
        # Home Chettinad-leaning masala with ground coconut and poppy seed.
        # The 600 g is BONELESS-EQUIVALENT edible weight: IFCT has no bone-in
        # composite, so 600 g of curry cut with bone is closer to 420 g here.
        yield_factor=1.10,
        serves=5,
        measures=[("1 serving", 255.0)],
        ingredients=[
            ("ifct:N001", 600.0),  # Chicken, leg, skinless
            ("ifct:G017", 200.0),
            ("ifct:D075", 150.0),
            ("ifct:H007", 60.0),
            ("ifct:T005", 45.0),
            ("ifct:G011", 20.0),
            ("ifct:G014", 20.0),
            ("ifct:G024", 15.0),
            ("ifct:G022", 12.0),
            ("manual:salt", 10.0),
            ("ifct:G009", 10.0),
            ("ifct:G010", 6.0),
            ("ifct:G025", 5.0),
            ("ifct:G031", 5.0),
            ("ifct:G032", 5.0),
            ("ifct:G033", 3.0),
            ("ifct:G020", 2.0),
            ("ifct:G023", 1.0),
        ],
    ),
    Recipe(
        code="si:egg_curry",
        name="Egg curry (muttai kuzhambu)",
        slot_tags="lunch dinner",
        diet_tags="eggetarian",
        yield_factor=1.40,
        serves=4,
        measures=[("1 serving (1 egg + gravy)", 225.0)],
        ingredients=[
            ("ifct:M001", 200.0),  # 4 eggs, edible portion
            ("ifct:G017", 150.0),
            ("ifct:D075", 150.0),
            ("ifct:H007", 50.0),
            ("ifct:T005", 30.0),
            ("ifct:G011", 12.0),
            ("ifct:G014", 10.0),
            ("ifct:G024", 10.0),
            ("ifct:G022", 8.0),
            ("manual:salt", 8.0),
            ("ifct:G009", 8.0),
            ("ifct:G010", 5.0),
            ("ifct:H013", 3.0),
            ("ifct:G033", 2.0),
        ],
    ),
    Recipe(
        code="si:omelette",
        name="Omelette",
        slot_tags="breakfast snack dinner",
        diet_tags="eggetarian",
        # Built from raw egg plus oil rather than IFCT's ready-made M007 omlet,
        # so the oil is explicit and adjustable. Sub-1.0: egg loses water.
        yield_factor=0.85,
        serves=1,
        measures=[("1 omelette (2 eggs)", 128.0)],
        ingredients=[
            ("ifct:M001", 100.0),
            ("ifct:G017", 30.0),
            ("ifct:T012", 8.0),
            ("ifct:G001", 5.0),
            ("ifct:G009", 4.0),
            ("manual:salt", 2.0),
            ("ifct:G031", 1.0),
        ],
    ),
    Recipe(
        code="si:egg_boiled",
        name="Boiled egg",
        slot_tags="breakfast snack",
        diet_tags="eggetarian",
        yield_factor=1.00,  # edible portion only; boiling changes weight negligibly
        serves=2,
        measures=[("1 egg", 50.0)],
        ingredients=[("ifct:M001", 100.0)],
    ),
]


# ---------------------------------------------------------------------------
# 6. Chutneys and podis
# ---------------------------------------------------------------------------
_CHUTNEYS: list[Recipe] = [
    Recipe(
        code="si:chutney_coconut",
        name="Coconut chutney",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # About half a coconut, ground with water to a spoonable consistency --
        # the water is why yield is 1.80.
        yield_factor=1.80,
        serves=6,
        measures=[("1 serving", 80.0), ("2 tbsp", 40.0)],
        ingredients=[
            ("ifct:H007", 200.0),
            ("ifct:B001", 30.0),  # proxy for roasted gram (pottukadalai)
            ("ifct:G001", 12.0),
            ("ifct:T001", 10.0),
            ("ifct:G014", 6.0),
            ("manual:salt", 4.0),
            ("ifct:B003", 4.0),
            ("ifct:H013", 3.0),
            ("ifct:G022", 3.0),
            ("ifct:G010", 3.0),
        ],
    ),
    Recipe(
        code="si:chutney_tomato",
        name="Tomato chutney",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=0.82,  # sauteed down before grinding, no water added
        serves=6,
        measures=[("1 serving", 70.0), ("2 tbsp", 40.0)],
        ingredients=[
            ("ifct:D075", 350.0),
            ("ifct:G017", 100.0),
            ("ifct:T004", 25.0),
            ("ifct:B003", 12.0),
            ("ifct:B001", 12.0),
            ("ifct:G022", 8.0),
            ("ifct:E064", 8.0),
            ("manual:salt", 5.0),
            ("ifct:H013", 3.0),
            ("ifct:G010", 3.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:chutney_coriander",
        name="Coriander chutney",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=1.55,
        serves=6,
        measures=[("1 serving", 70.0), ("2 tbsp", 35.0)],
        ingredients=[
            ("ifct:G009", 120.0),  # two large bunches, stalks discarded
            ("ifct:H007", 80.0),
            ("ifct:B003", 15.0),
            ("ifct:B001", 15.0),
            ("ifct:T004", 15.0),
            ("ifct:G001", 12.0),
            ("ifct:E064", 8.0),
            ("manual:salt", 4.0),
            ("ifct:H013", 3.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:chutney_mint",
        name="Mint chutney",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=1.45,
        serves=6,
        measures=[("1 serving", 75.0), ("2 tbsp", 35.0)],
        ingredients=[
            ("ifct:G016", 100.0),
            ("ifct:H007", 80.0),
            ("ifct:G017", 40.0),
            ("ifct:G009", 30.0),
            ("ifct:B003", 15.0),
            ("ifct:T004", 15.0),
            ("ifct:G001", 12.0),
            ("ifct:E064", 8.0),
            ("manual:salt", 4.0),
            ("ifct:H013", 3.0),
        ],
    ),
    Recipe(
        code="si:chutney_onion",
        name="Onion chutney (vengaya chutney)",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        yield_factor=0.84,  # shallots sauteed till soft, ground thick
        serves=6,
        measures=[("2 tbsp", 40.0)],
        ingredients=[
            ("ifct:G018", 250.0),
            ("ifct:T004", 25.0),
            ("ifct:B003", 12.0),
            ("ifct:E064", 10.0),
            ("ifct:G022", 8.0),
            ("manual:salt", 5.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:sambar_powder",
        name="Sambar powder",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # Sub-1.0 is moisture driven off during dry-roasting (~8%).
        # A store-cupboard item, not a meal: `serves` counts teaspoons in the
        # batch (561 g / 4 g), which is the only honest reading of "serves" for
        # a spice tin. Slot tags name the meals it appears in.
        yield_factor=0.92,
        serves=140,
        measures=[("1 tsp", 4.0), ("1 tbsp", 12.0)],
        ingredients=[
            ("ifct:G024", 250.0),
            ("ifct:G022", 150.0),
            ("ifct:B021", 50.0),
            ("ifct:B001", 50.0),
            ("ifct:G033", 30.0),
            ("ifct:G025", 25.0),
            ("ifct:G026", 20.0),
            ("ifct:G031", 20.0),
            ("ifct:G010", 10.0),
            ("ifct:G019", 5.0),
        ],
    ),
    Recipe(
        code="si:rasam_powder",
        name="Rasam powder",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        yield_factor=0.92,  # pepper- and cumin-forward, far less chilli than sambar powder
        serves=105,
        measures=[("1 tsp", 4.0), ("1 tbsp", 12.0)],
        ingredients=[
            ("ifct:G024", 200.0),
            ("ifct:G031", 60.0),
            ("ifct:G025", 60.0),
            ("ifct:G022", 60.0),
            ("ifct:B021", 40.0),
            ("ifct:G033", 15.0),
            ("ifct:G026", 10.0),
            ("ifct:G010", 10.0),
        ],
    ),
    Recipe(
        code="si:idli_podi",
        name="Idli podi (milagai podi)",
        slot_tags="breakfast snack dinner",
        diet_tags=VEG,
        # The gingelly oil it is mixed with at the plate is NOT included: that
        # amount is per person, so log the oil separately.
        yield_factor=0.93,
        serves=68,
        measures=[("1 tsp", 5.0), ("1 tbsp", 15.0)],
        ingredients=[
            ("ifct:B003", 150.0),
            ("ifct:B001", 100.0),
            ("ifct:G022", 60.0),
            ("ifct:H011", 30.0),  # Gingelly seeds
            ("manual:salt", 12.0),
            ("ifct:T004", 10.0),
            ("ifct:G019", 3.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 7. Fried snacks
#
# The oil listed is the oil ABSORBED BY THE FOOD, not the oil in the kadai.
# Every recipe states its retention as a percentage of finished weight, because
# this assumption is the largest error source in the whole data set and moving
# it by 5 points moves six dishes' fat and calories by up to 50%. Published
# figures for Indian fried snacks span 8-25%; these sit at 11-18%.
# ---------------------------------------------------------------------------
_FRIED: list[Recipe] = [
    Recipe(
        code="si:medu_vada",
        name="Medu vada",
        slot_tags="breakfast snack",
        diet_tags=VEG,
        # Above 1.0 because the ground batter holds water even after frying.
        # DEEP-FRY OIL RETENTION: 60 g of 534 g finished = 11%.
        yield_factor=1.30,
        serves=12,
        measures=[("1 vada", 45.0), ("2 vada", 90.0)],
        ingredients=[
            ("ifct:B003", 250.0),  # 250 g urad dal makes 12 vadas
            ("ifct:G017", 60.0),
            ("ifct:T005", 60.0),  # absorbed groundnut oil
            ("ifct:G001", 10.0),
            ("ifct:G014", 8.0),
            ("ifct:G009", 6.0),
            ("manual:salt", 6.0),
            ("ifct:G010", 5.0),
            ("ifct:G031", 3.0),
            ("ifct:G025", 3.0),
        ],
    ),
    Recipe(
        code="si:masala_vada",
        name="Masala vada (paruppu vadai)",
        slot_tags="snack",
        diet_tags=VEG,
        # Yield ~1.0: coarse dal holds less water than fine urad batter and
        # frying dries it out.
        # DEEP-FRY OIL RETENTION: 65 g of 502 g finished = 13%.
        yield_factor=1.02,
        serves=12,
        measures=[("1 vada", 42.0), ("2 vada", 84.0)],
        ingredients=[
            ("ifct:B001", 250.0),
            ("ifct:G017", 80.0),
            ("ifct:T005", 65.0),  # absorbed
            ("ifct:B021", 50.0),
            ("ifct:G022", 10.0),
            ("ifct:G001", 8.0),
            ("ifct:G009", 8.0),
            ("ifct:G014", 6.0),
            ("ifct:G010", 6.0),
            ("manual:salt", 6.0),
            ("ifct:G026", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:bonda",
        name="Bonda (aloo bonda)",
        slot_tags="snack",
        diet_tags=VEG,
        # Sub-1.0: the potato filling is already cooked and the thin batter
        # shell loses its water in the oil.
        # DEEP-FRY OIL RETENTION: 75 g of 690 g finished = 11%.
        yield_factor=0.90,
        serves=10,
        measures=[("1 bonda", 70.0), ("2 bonda", 140.0)],
        ingredients=[
            ("ifct:F006", 400.0),
            ("ifct:B001", 150.0),  # proxy for besan
            ("ifct:G017", 100.0),
            ("ifct:T005", 75.0),  # absorbed
            ("ifct:G001", 10.0),
            ("ifct:G014", 8.0),
            ("ifct:G009", 8.0),
            ("manual:salt", 6.0),
            ("ifct:H013", 4.0),
            ("ifct:G010", 4.0),
            ("ifct:G033", 2.0),
        ],
    ),
    Recipe(
        code="si:bajji",
        name="Bajji (plantain)",
        slot_tags="snack",
        diet_tags=VEG,
        # DEEP-FRY OIL RETENTION: 90 g of 508 g finished = 18%. The thirstiest
        # item in the set -- bajji batter is a sponge -- and therefore the one
        # most worth re-measuring if the fat numbers look wrong.
        # Cooking soda is omitted (no IFCT row), so bajji sodium is slightly low.
        yield_factor=0.90,
        serves=12,
        measures=[("1 bajji", 42.0), ("3 bajji", 126.0)],
        ingredients=[
            ("ifct:D063", 250.0),
            ("ifct:B001", 180.0),  # proxy for besan
            ("ifct:T005", 90.0),  # absorbed
            ("ifct:A015", 30.0),  # proxy for rice flour
            ("ifct:G022", 6.0),
            ("manual:salt", 5.0),
            ("ifct:G033", 2.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:murukku",
        name="Murukku (thenkuzhal)",
        slot_tags="snack",
        diet_tags=VEG,
        # 4:1 rice flour to urad flour, the thenkuzhal ratio, ~24 pieces.
        # Sub-1.0 because the finished murukku is dry and crisp.
        # DEEP-FRY OIL RETENTION: 90 g of 609 g finished = 15%.
        yield_factor=0.95,
        serves=24,
        measures=[("1 murukku", 25.0), ("2 murukku", 50.0)],
        ingredients=[
            ("ifct:A015", 400.0),  # proxy for rice flour
            ("ifct:B003", 100.0),  # proxy for urad flour
            ("ifct:T005", 90.0),  # absorbed
            ("ifct:T013", 25.0),
            ("ifct:H011", 10.0),
            ("manual:salt", 8.0),
            ("ifct:G025", 6.0),
            ("ifct:G019", 2.0),
        ],
    ),
]


# ---------------------------------------------------------------------------
# 8. Drinks
#
# COFFEE AND TEA ARE BUILT FROM BREWED LIQUID. The naive model -- listing 24 g
# of coffee powder as an ingredient -- credits the cup with the protein, fat,
# fibre, magnesium and potassium of grounds that are steeped and thrown away.
# Only the water-soluble extractives reach the tumbler. So the decoction and the
# tea are ingredients in their own right, priced per 100 g of LIQUID
# (usda:coffee_brewed, usda:tea_brewed), with milk and sugar listed separately.
#
# yield_factor is 1.00 for all four: every ingredient is already a liquid at its
# final strength, so nothing is absorbed and nothing boils off.
#
# Known conservatism: the USDA rows are US drip strength. South Indian filter
# decoction is roughly three times stronger before it is cut with milk, so the
# coffee-derived micronutrients are understated by about that factor -- of the
# order of 50 mg potassium per tumbler. Energy, fat and protein are unaffected
# because brewed coffee is 99% water and the milk and sugar dominate.
# ---------------------------------------------------------------------------
_DRINKS: list[Recipe] = [
    Recipe(
        code="si:filter_coffee_sugar",
        name="Filter coffee, with sugar",
        slot_tags="breakfast snack",
        diet_tags=VEG,
        yield_factor=1.00,
        serves=4,
        measures=[("1 tumbler (150 ml)", 158.0), ("1 small cup", 105.0)],
        ingredients=[
            ("ifct:L002", 400.0),  # ~100 ml milk per tumbler
            ("usda:coffee_brewed", 200.0),  # ~50 ml decoction per tumbler
            ("manual:sugar", 32.0),  # 2 tsp per tumbler
        ],
    ),
    Recipe(
        code="si:filter_coffee_plain",
        name="Filter coffee, no sugar",
        slot_tags="breakfast snack",
        diet_tags=VEG,
        yield_factor=1.00,
        serves=4,
        measures=[("1 tumbler (150 ml)", 150.0), ("1 small cup", 100.0)],
        ingredients=[
            ("ifct:L002", 400.0),
            ("usda:coffee_brewed", 200.0),
        ],
    ),
    Recipe(
        code="si:tea",
        name="Tea, with sugar",
        slot_tags="snack",
        diet_tags=VEG,
        # Less milk and more water than coffee -- the reverse of the filter
        # coffee proportions.
        yield_factor=1.00,
        serves=4,
        measures=[("1 cup", 158.0)],
        ingredients=[
            ("ifct:L002", 240.0),  # ~60 ml milk per cup
            ("usda:tea_brewed", 360.0),  # ~90 ml brewed tea per cup
            ("manual:sugar", 32.0),
        ],
    ),
    Recipe(
        code="si:tea_no_sugar",
        name="Tea, no sugar",
        slot_tags="snack",
        diet_tags=VEG,
        yield_factor=1.00,
        serves=4,
        measures=[("1 cup", 150.0)],
        ingredients=[
            ("ifct:L002", 240.0),
            ("usda:tea_brewed", 360.0),
        ],
    ),
    Recipe(
        code="si:neer_mor",
        name="Neer mor (spiced buttermilk)",
        slot_tags="snack lunch",
        diet_tags=VEG,
        # Built from curd, not a separate buttermilk ingredient: the ~1:3
        # dilution IS what the yield factor expresses, so no hand-derived
        # manual:buttermilk needs to exist.
        yield_factor=3.70,
        serves=4,
        measures=[("1 glass (250 ml)", 250.0)],
        ingredients=[
            ("usda:curd", 250.0),
            ("ifct:G014", 5.0),
            ("ifct:G001", 4.0),
            ("manual:salt", 3.0),
            ("ifct:G010", 3.0),
            ("ifct:G009", 3.0),
            ("ifct:G019", 1.0),
        ],
    ),
    Recipe(
        code="si:ragi_kanji",
        name="Ragi kanji (sweet)",
        slot_tags="breakfast snack",
        diet_tags=VEG,
        yield_factor=1.85,
        serves=2,
        measures=[("1 glass", 265.0)],
        ingredients=[
            ("ifct:L002", 200.0),
            ("ifct:A010", 60.0),  # Ragi
            ("ifct:I001", 30.0),
        ],
    ),
    Recipe(
        code="si:curd_side",
        name="Curd (plain, as a side)",
        slot_tags="lunch dinner",
        diet_tags=VEG,
        # A single-ingredient dish so the end-of-meal curd is one tap.
        yield_factor=1.00,
        serves=1,
        measures=[("1 cup", 150.0), ("1/2 cup", 75.0)],
        ingredients=[("usda:curd", 150.0)],
    ),
]


# ---------------------------------------------------------------------------
# 9. Sweets
#
# These are logged as ordinary meals, not as festival food, so the defaults are
# the everyday home versions. A festival ratio left in as the default would
# silently overstate calories every single time the dish is logged.
# ---------------------------------------------------------------------------
_SWEETS: list[Recipe] = [
    Recipe(
        code="si:payasam_semiya",
        name="Semiya payasam",
        slot_tags="snack lunch dinner",
        diet_tags=VEG,
        # Barely above 1.0: the vermicelli absorbs the milk rather than added
        # water, and some milk boils off.
        yield_factor=1.05,
        serves=6,
        measures=[("1 cup", 190.0)],
        ingredients=[
            ("ifct:L002", 800.0),
            ("manual:sugar", 120.0),
            ("ifct:A024", 100.0),
            ("ifct:T013", 25.0),
            ("ifct:H005", 25.0),
            ("ifct:E057", 20.0),
            ("ifct:G020", 2.0),
        ],
    ),
    Recipe(
        code="si:payasam_paruppu",
        name="Paruppu payasam",
        slot_tags="snack lunch dinner",
        diet_tags=VEG,
        # Jaggery and coconut milk version. Coconut milk is entered as fresh
        # kernel, which is how it is extracted at home; that overstates fibre,
        # because the squeezed residue is really discarded.
        yield_factor=1.50,
        serves=6,
        measures=[("1 cup", 180.0)],
        ingredients=[
            ("ifct:L002", 300.0),
            ("ifct:I001", 200.0),
            ("ifct:B010", 100.0),
            ("ifct:H007", 80.0),
            ("ifct:T013", 25.0),
            ("ifct:H005", 20.0),
            ("ifct:G020", 2.0),
        ],
    ),
    Recipe(
        code="si:kesari",
        name="Rava kesari",
        slot_tags="snack breakfast",
        diet_tags=VEG,
        # GHEE: 50 g, not the 100 g first drafted. 1 : 1.5 : 0.5 rava : sugar :
        # ghee is the festival/restaurant ratio; the home version uses half the
        # ghee, which takes ~55 kcal per piece off a dish eaten at breakfast.
        # Yield drops from 1.55 to 1.60 on the smaller raw base because the same
        # water still goes into the rava.
        yield_factor=1.60,
        serves=8,
        measures=[("1 piece", 120.0)],
        ingredients=[
            ("manual:sugar", 300.0),
            ("ifct:A022", 200.0),
            ("ifct:T013", 50.0),
            ("ifct:H005", 25.0),
            ("ifct:E057", 15.0),
            ("ifct:G020", 2.0),
        ],
    ),
]


RECIPES: list[Recipe] = [
    *_TIFFIN,
    *_RICE,
    *_KUZHAMBU,
    *_VEGETABLES,
    *_FISH,
    *_OTHER_NONVEG,
    *_CHUTNEYS,
    *_FRIED,
    *_DRINKS,
    *_SWEETS,
]
