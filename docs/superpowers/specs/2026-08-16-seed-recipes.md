# Seed recipes — South Indian dishes

**Status:** REVIEWED and CODED. This document now describes what
`backend/etl/recipes/south_indian.py` actually contains. The two must stay in step:
this is the record a cook can check, the module is what the app computes from.

## What you are looking at

72 dishes, each broken into raw ingredients with gram weights for one batch. Every
nutrient number the app shows — your sodium, your protein, your calories — is computed
from these grams. Nothing is copied from a label. If a number here is wrong, every meal
you log with that dish is wrong by the same proportion, forever.

## What the review changed

The draft had 66 dishes. Six decisions came back, and all six are now in the code:

| # | Decision | Effect |
|---|---|---|
| 1 | **Idli/dosa batter is 4:1, not 3:1** | Urad dal drops from 125 g to 95 g per 400 g rice in idli, plain dosa, masala dosa and uttapam. Cooked weights, yields, serves and measures all recomputed — no stale arithmetic left behind. |
| 2 | **Sweets use the everyday version** | Kesari ghee 100 g → 50 g; sakkarai pongal jaggery 250 g → 150 g; ven pongal ghee 45 g → 30 g. These are logged as ordinary meals, so a festival ratio as the default overstates calories every single time. |
| 3 | **Rasam stays as drafted** | Tomato 3.30, pepper 5.75, lemon 4.45 — unchanged. |
| 4 | **Fish is a variant set, not one species** | Fish kuzhambu and fish fry each ship in four species (vanjaram, sardine, mackerel, nethili). 66 dishes → 72. |
| 5 | **Coffee and tea use brewed liquid** | `usda:coffee_brewed` and `usda:tea_brewed` replace the "24 g of coffee powder" model, which credited the cup with grounds that are thrown away. |
| 6 | **Tamarind pulp is `ifct:E064`** | Confirmed present. No `manual:tamarind_pulp` was created; all 14 dishes use the real code (11 recipes before the fish variants — the draft's count of nine was low). |

Plus three structural rulings: the yield factor is cooked ÷ raw-DRY-ingredients (so a
dosa is 1.70, not sub-1.0); composite condiments stay inlined rather than nesting dishes;
and the proxy substitutions (rice flour, besan, roasted gram, urad flour, coconut milk)
are accepted with their notes kept.

## Fix round 1 — defects found reviewing the coded result

| # | Defect | Fix |
|---|---|---|
| 1 | **CRITICAL: every oil and ghee had 0 kcal.** All 14 rows of IFCT's "Edible Oils and Fats" group publish `enerc=0` alongside `fatce=100`. Taken literally that zeroes the calories of the most energy-dense thing in the pantry, and because nearly all South Indian cooking is oil-tempered it understated 40+ dishes by 30–112%. | Fixed in the **ingredient layer**, not here — the recipe grams were right. `etl/load_ifct.py` now derives energy from the food's own macros with Atwater factors (4/4/9 kcal per g) whenever IFCT publishes a zero its own macro row contradicts, tagged `derived:atwater` so the substitution is visible. A guard test asserts no food in the real 542-row dataset can have zero energy while its macros imply more than 20 kcal/100 g. |
| 2 | **Chutney default portion was double the reviewed one.** `load_recipes` marks `measures[0]` as the default, and the code listed the 70–80 g "1 serving" first, so the app pre-selected roughly double what this document bolds. | The 40 g / 35 g "2 tbsp" measure is now first for all four ground chutneys, and `serves` follows it. Two tests pin it: one on the recipe data, one proving the loader honours the order. |
| 3 | **The two pongals disagreed about ghee.** Ven pongal was cut to 6 g of ghee per serving while sakkarai pongal kept 10 g. | Sakkarai pongal's ghee 60 g → **45 g** (7.5 g per serving). Yield 1.75 → 1.77. A test asserts the two stay levelled. |
| 4 | **Seven dishes were 25–50% saltier than home practice**, all from one mechanical cause: salt set per raw batch without rechecking concentration after a sub-1.0 yield factor concentrates it. The tell was an inversion — a 110 g vegetable side out-salting a full cup of sambar. | Omelette 2 → 0.8 g, the three poriyals and thoran 5 → 3 g, rava dosa 8 → 5.5 g, adai 10 → 7.5 g, onion chutney 5 → 3 g, plus **fish fry 6 → 4.5 g and murukku 8 → 7 g**, which the new invariant caught and the review had not listed. An invariant test now caps salt at **1.2% of finished weight** for every non-powder dish. |

**The salt grams were NOT cut across the board, deliberately.** Sambar's 10 g in a 1.5 L
pot is 0.66% NaCl, at or below normal palatability; idli works out to 0.34 g of salt per
idli, which matches published recipes; a modelled day totals ~9.9 g, squarely inside
measured Indian intake of 8–11 g/day. Only the outliers moved.

**Five manual ingredients now exist** in `backend/etl/load_manual_ingredients.py`:
`manual:salt`, `usda:curd`, `manual:sugar`, `usda:coffee_brewed`, `usda:tea_brewed`.
`manual:buttermilk` was deliberately NOT created — neer mor is curd plus dilution
expressed through the yield factor. See "Resolutions A" at the end for each one's
cited source.

---

## Conventions used throughout

**Yield factor** = cooked batch weight ÷ sum of the raw ingredient grams.

Ingredient weights are **raw and dry**. Water added during cooking is *not* an
ingredient — it enters the model only through the yield factor. That is why rasam,
which is mostly water, has a yield factor of 3.3 to 5.8, and why every steamed or
boiled grain dish exceeds 1.0.

> **Ruling (applied).** Task 6's brief said "a dosa loses water so sits below 1.0".
> That only holds if the raw basis is *batter*. On a dry-grain basis a plain dosa
> lands at 1.70, because 400 g of dry rice becomes roughly a kilo of dosas. The
> dry-grain reading is the one used throughout. Genuinely sub-1.0 dishes are the ones
> that are dry-fried or crisped: rava dosa (0.95), poriyal (0.75–0.88), murukku (0.95),
> bajji and bonda (0.90), fish fry (0.80), omelette (0.85).

**`Serves`** is the number of DEFAULT-measure portions in one batch, so
`default measure × serves` reconstructs the cooked weight. That is why idli "serves 29"
(29 idlis) rather than "serves 10 people", and why sambar powder "serves 140" — a spice
tin is not eaten in meals, and a fictional per-person number would be worse than a
large honest one. A test asserts this reconstruction holds for all 72 dishes.

**Volume-to-weight conversions** (240 ml cup) used to convert published recipes:

| Item | 1 cup | 1 tbsp | 1 tsp |
|---|---|---|---|
| Raw / parboiled rice | 200 g | — | — |
| Urad dal | 190 g | — | — |
| Toor / channa dal | 200 g | — | — |
| Rava (semolina) | 170 g | — | — |
| Grated fresh coconut | 80 g | — | — |
| Milk / curd | 240 g | — | — |
| Sugar | 200 g | — | 4 g |
| Jaggery | 180 g | — | — |
| Oil / ghee | — | 14 g | 4.5 g |
| Mustard, cumin, turmeric | — | — | 3–4 g |
| Salt | — | — | 6 g |

**Deep-fried items.** Only the oil that stays *in* the food is listed, not the oil in the
kadai. Assumption **kept as drafted after review**: batter-fried items retain **11–18% of
their finished weight** as oil — medu vada 11%, masala vada 13%, bonda 11%, bajji 18%,
murukku 15%, fish fry 10%. Published figures for Indian fried snacks span 8–25%, so this
is the single largest error source in the whole document; moving it 5 points moves six
dishes' fat and calories by up to 50%. **Every fried recipe in the code carries its
retention percentage in a comment**, so the assumption is auditable and revisable in one
place rather than buried in a gram count.

**Composite condiments are inlined.** The `Recipe` model references *ingredients*, not
other dishes. So sambar cannot say "12 g sambar powder"; it has to list the coriander
seeds, red chilli and so on directly. Sambar powder also exists as its own dish for
when you log a spoonful. The spices therefore appear twice in the seed set — that is
intentional, not a duplicate.

**Regional variant.** Where a dish varies, I used the common **Tamil Nadu** home
version. Thoran is the one deliberate exception (Kerala), included because the brief
asked for it.

**Codes.** Every `ifct:` code below was checked against the live 542-row `ingredients`
table. The five non-IFCT codes (`manual:salt`, `usda:curd`, `manual:sugar`,
`usda:coffee_brewed`, `usda:tea_brewed`) now exist too — see "Resolutions A" for the
cited source behind each. A test fails the build on any code that is not in the database.

---

# 1. Tiffin / breakfast items

> **The shared batter (decision 1).** Idli, plain dosa, masala dosa and uttapam are all
> the same batter: **4:1 parboiled rice to urad dal by volume**, which is 400 g rice to
> **95 g** dal by weight, plus a little fenugreek for the ferment. The draft used 3:1
> (400:125); the review corrected it. This is eaten daily, so 30 g of extra dal per batch
> would have inflated the protein in every breakfast the app ever logged.

### Idli — `si:idli`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 29 (idlis) · Yield **2.60** · Raw batch 510 g → 1326 g cooked
Measures: **1 idli = 45 g** · 2 idli = 90 g · 3 idli = 135 g
Basis: the 4:1 batter. Batch is ~29 idlis. Yield is high because dry grain is soaked,
ground with water and steamed.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 400 |
| Black gram, dal (urad) | `ifct:B003` | 95 |
| Fenugreek seeds | `ifct:G026` | 5 |
| Salt | `manual:salt` | 10 |

### Plain dosa — `si:dosa_plain`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 15 (dosas) · Yield **1.70** · Raw 542 g → 921 g
Measures: **1 dosa = 60 g** · 2 dosa = 120 g
Basis: the same 4:1 batter, ground thinner. ~15 dosas. Oil is the ~2 g per dosa
smeared on the tawa. Yield lower than idli because the thin batter loses water on the griddle.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 400 |
| Black gram, dal | `ifct:B003` | 95 |
| Fenugreek seeds | `ifct:G026` | 5 |
| Salt | `manual:salt` | 10 |
| Gingelly oil | `ifct:T004` | 32 |

### Masala dosa — `si:dosa_masala`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 8 · Yield **1.00** · Raw 1252 g → 1252 g
Measures: **1 masala dosa = 160 g** (≈60 g dosa + ≈100 g potato masala)
Basis: two-thirds of a batter batch (at the same 4:1 ratio) plus a standard potato
masala. Yield sits at 1.00 because the potato masala dominates and potato neither gains
nor loses much weight, cancelling the batter's gain.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 270 |
| Black gram, dal | `ifct:B003` | 64 |
| Fenugreek seeds | `ifct:G026` | 4 |
| Potato, brown skin, big | `ifct:F006` | 600 |
| Onion, big | `ifct:G017` | 200 |
| Sunflower oil | `ifct:T012` | 50 |
| Salt | `manual:salt` | 14 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Bengal gram, dal | `ifct:B001` | 10 |
| Coriander leaves | `ifct:G009` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Turmeric powder | `ifct:G033` | 2 |

### Rava dosa — `si:dosa_rava`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 4 · Yield **0.95** · Raw 502 g → 477 g
Measures: **2 rava dosa = 120 g** · 1 rava dosa = 60 g
Basis: standard 3:2:1 rava : rice flour : maida. Batter is poured, not spread, and cooked
lace-thin and crisp — it ends up *lighter* than its dry ingredients plus oil, hence sub-1.0.
Rice flour is entered as raw milled rice (see resolutions A).

| Ingredient | Code | Raw g |
|---|---|---:|
| Wheat, semolina | `ifct:A022` | 150 |
| Rice, raw, milled *(as rice flour)* | `ifct:A015` | 100 |
| Onion, big | `ifct:G017` | 100 |
| Sunflower oil | `ifct:T012` | 60 |
| Wheat flour, refined | `ifct:A018` | 50 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Salt | `manual:salt` | 5.5 |
| Coriander leaves | `ifct:G009` | 8 |
| Cumin seeds | `ifct:G025` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Pepper, black | `ifct:G031` | 3 |

### Adai — `si:adai`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 8 · Yield **1.25** · Raw 606 g → 757 g
Measures: **1 adai = 95 g**
Basis: 1 cup rice to 1 cup mixed dals, the usual Tamil proportion. Coarse-ground, thick,
griddled — absorbs less than idli, more than a thin dosa.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 200 |
| Onion, big | `ifct:G017` | 100 |
| Red gram, dal (toor) | `ifct:B021` | 60 |
| Bengal gram, dal | `ifct:B001` | 60 |
| Black gram, dal | `ifct:B003` | 40 |
| Green gram, dal | `ifct:B010` | 40 |
| Coconut, kernel, fresh | `ifct:H007` | 40 |
| Gingelly oil | `ifct:T004` | 40 |
| Chillies, red | `ifct:G022` | 12 |
| Salt | `manual:salt` | 7.5 |
| Curry leaves | `ifct:G010` | 5 |
| Asafoetida | `ifct:G019` | 1 |

### Uttapam (onion-tomato) — `si:uttapam`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 6 · Yield **1.55** · Raw 653 g → 1012 g
Measures: **1 uttapam = 170 g**
Basis: three-quarters of a batter batch (at the same 4:1 ratio) poured thick with the
topping pressed in. Thicker than dosa so it retains more water, but less than a steamed idli.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 300 |
| Onion, big | `ifct:G017` | 120 |
| Tomato, ripe, hybrid | `ifct:D075` | 100 |
| Black gram, dal | `ifct:B003` | 71 |
| Sunflower oil | `ifct:T012` | 30 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Coriander leaves | `ifct:G009` | 10 |
| Salt | `manual:salt` | 8 |
| Fenugreek seeds | `ifct:G026` | 4 |

### Ven pongal — `si:ven_pongal`
Slots: breakfast, mid-morning snack, dinner · Vegetarian · Serves 5 · Yield **2.60** · Raw 427 g → 1110 g
Measures: **1 cup = 220 g** · ½ cup = 110 g
Basis: 3:1 rice to moong dal by volume, cooked soft with roughly 4 parts water.
**Ghee reduced 45 g → 30 g (decision 2).** 45 g for 5 servings is 9 g (2 tsp) of ghee per
serving — a temple or restaurant pongal. 30 g is 6 g per serving, which is what a weekday
morning actually gets. This is logged as an ordinary breakfast, so the default has to be
the ordinary version.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 250 |
| Green gram, dal (moong) | `ifct:B010` | 85 |
| Ghee | `ifct:T013` | 30 |
| Cashew nut | `ifct:H005` | 25 |
| Ginger, fresh | `ifct:G014` | 12 |
| Salt | `manual:salt` | 8 |
| Pepper, black | `ifct:G031` | 6 |
| Cumin seeds | `ifct:G025` | 5 |
| Curry leaves | `ifct:G010` | 5 |
| Asafoetida | `ifct:G019` | 1 |

### Sakkarai pongal — `si:sakkarai_pongal`
Slots: breakfast, mid-morning snack, evening snack · Vegetarian · Serves 6 · Yield **1.77** · Raw 607 g → 1074 g
Measures: **1 cup = 180 g** · ½ cup = 90 g
Basis: rice : moong dal 3:1. **Jaggery reduced 250 g → 150 g (decision 2)** — 250 g had
the jaggery exceeding the combined grain weight, a festival prasadam ratio; 150 g is the
home version and takes about 65 kcal per serving off a dish people log as breakfast.
Yield lower than ven pongal because jaggery, ghee and milk are already-heavy ingredients
that do not swell.
**Ghee reduced 60 g → 45 g**, so both pongals sit at the same everyday standard —
7.5 g of ghee per serving here, 6 g in ven pongal. The first pass flagged this rather than
changing it silently, because the original ruling named only the jaggery; the follow-up
ruling levelled the two.

| Ingredient | Code | Raw g |
|---|---|---:|
| Jaggery, cane | `ifct:I001` | 150 |
| Rice, raw, milled | `ifct:A015` | 200 |
| Milk, whole, Cow | `ifct:L002` | 100 |
| Green gram, dal | `ifct:B010` | 60 |
| Ghee | `ifct:T013` | 45 |
| Cashew nut | `ifct:H005` | 30 |
| Raisins, dried, black | `ifct:E057` | 20 |
| Cardamom, green | `ifct:G020` | 2 |

### Upma (rava) — `si:upma`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 4 · Yield **1.95** · Raw 381 g → 743 g
Measures: **1 cup = 185 g**
Basis: rava to water 1:2.5 by volume, the standard. Rava roughly triples in weight.

| Ingredient | Code | Raw g |
|---|---|---:|
| Wheat, semolina | `ifct:A022` | 200 |
| Onion, big | `ifct:G017` | 100 |
| Sunflower oil | `ifct:T012` | 25 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Coriander leaves | `ifct:G009` | 8 |
| Bengal gram, dal | `ifct:B001` | 8 |
| Black gram, dal | `ifct:B003` | 8 |
| Salt | `manual:salt` | 6 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |

### Semiya upma — `si:semiya_upma`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 4 · Yield **1.70** · Raw 438 g → 745 g
Measures: **1 cup = 185 g**
Basis: roasted vermicelli to water 1:2. Absorbs less than rava.

| Ingredient | Code | Raw g |
|---|---|---:|
| Wheat, vermicelli, roasted | `ifct:A024` | 200 |
| Onion, big | `ifct:G017` | 80 |
| Carrot, orange | `ifct:F002` | 60 |
| Peas, fresh | `ifct:D061` | 40 |
| Sunflower oil | `ifct:T012` | 22 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Salt | `manual:salt` | 6 |
| Black gram, dal | `ifct:B003` | 6 |
| Bengal gram, dal | `ifct:B001` | 6 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |

### Idiyappam — `si:idiyappam`
Slots: breakfast, dinner · Vegetarian · Serves 4 · Yield **2.35** · Raw 315 g → 740 g
Measures: **3 idiyappam = 180 g** · 1 idiyappam = 60 g
Basis: rice flour kneaded with hot water and steamed — pure absorption, nothing lost.
12 pieces. Rice flour entered as raw milled rice (see resolutions A).

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled *(as rice flour)* | `ifct:A015` | 300 |
| Coconut oil | `ifct:T001` | 10 |
| Salt | `manual:salt` | 5 |

### Appam — `si:appam`
Slots: breakfast, dinner · Vegetarian · Serves 5 · Yield **1.70** · Raw 435 g → 740 g
Measures: **2 appam = 150 g** · 1 appam = 75 g
Basis: rice-and-coconut fermented batter, 10 appam. Lower than idiyappam because the
appam is cooked open-faced and its lacy edge dries out.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 300 |
| Coconut, kernel, fresh | `ifct:H007` | 100 |
| Sugar | `manual:sugar` | 15 |
| Coconut oil | `ifct:T001` | 15 |
| Salt | `manual:salt` | 5 |

### Puttu — `si:puttu`
Slots: breakfast, dinner · Vegetarian · Serves 4 · Yield **1.90** · Raw 405 g → 770 g
Measures: **1 puttu cylinder = 190 g**
Basis: rice flour moistened to breadcrumb texture, layered with coconut, steamed.
Absorbs less water than idiyappam because the flour is only damp, never a dough.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled *(as puttu flour)* | `ifct:A015` | 300 |
| Coconut, kernel, fresh | `ifct:H007` | 100 |
| Salt | `manual:salt` | 5 |

---

# 2. Rice dishes

### Plain rice (raw milled) — `si:rice_plain`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **2.90** · Raw 300 g → 870 g
Measures: **1 cup = 200 g** · 1 ladle = 150 g
Basis: standard absorption cooking of raw milled rice. 1 g dry → 2.9 g cooked.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 300 |

### Plain rice, parboiled (puzhungal arisi) — `si:rice_parboiled`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **3.00** · Raw 300 g → 900 g
Measures: **1 cup = 210 g** · 1 ladle = 150 g
Basis: parboiled rice takes marginally more water than raw milled. Kept as a separate
dish because the everyday Tamil Nadu rice is parboiled, not raw.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 300 |

### Kanji (rice gruel) — `si:kanji`
Slots: breakfast, dinner · Vegetarian · Serves 2 · Yield **6.00** · Raw 103 g → 618 g
Measures: **1 bowl = 300 g**
Basis: rice boiled in ~6 parts water and not drained. Very high yield because it is
mostly the cooking water, which is drunk rather than discarded.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, parboiled, milled | `ifct:A014` | 100 |
| Salt | `manual:salt` | 3 |

### Curd rice (thayir sadam) — `si:curd_rice`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **1.50** · Raw 744 g → 1116 g
Measures: **1 cup = 280 g**
Basis: 1 cup raw rice to 1.7 cups curd, mashed soft, with milk to loosen. Yield is
modest because curd and milk are already wet — only the rice swells.

| Ingredient | Code | Raw g |
|---|---|---:|
| Curd, whole cow milk | `usda:curd` | 400 |
| Rice, raw, milled | `ifct:A015` | 200 |
| Milk, whole, Cow | `ifct:L002` | 100 |
| Sunflower oil | `ifct:T012` | 10 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Ginger, fresh | `ifct:G014` | 8 |
| Coriander leaves | `ifct:G009` | 6 |
| Salt | `manual:salt` | 5 |
| Mustard seeds | `ifct:H013` | 3 |
| Curry leaves | `ifct:G010` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Lemon rice — `si:lemon_rice`
Slots: lunch, evening snack, dinner · Vegetarian · Serves 4 · Yield **2.10** · Raw 415 g → 872 g
Measures: **1 cup = 220 g**
Basis: cooked rice from 250 g raw, tossed with a tempering and the juice of ~2 limes (45 g).

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 250 |
| Lemon, juice | `ifct:E033` | 45 |
| Gingelly oil | `ifct:T004` | 35 |
| Ground nut | `ifct:H012` | 25 |
| Bengal gram, dal | `ifct:B001` | 12 |
| Black gram, dal | `ifct:B003` | 10 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Chillies, red | `ifct:G022` | 6 |
| Salt | `manual:salt` | 6 |
| Coriander leaves | `ifct:G009` | 6 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Tamarind rice (puliyodharai) — `si:tamarind_rice`
Slots: lunch, evening snack · Vegetarian · Serves 5 · Yield **2.00** · Raw 530 g → 1060 g
Measures: **1 cup = 210 g**
Basis: rice plus a reduced pulikachal paste. Gingelly oil at 60 g is deliberately high —
puliyodharai is an oil-preserved dish and this is not a place to under-report.
**Tamarind pulp does exist in IFCT** as `ifct:E064`, contrary to the codes brief.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 300 |
| Tamarind, pulp | `ifct:E064` | 60 |
| Gingelly oil | `ifct:T004` | 60 |
| Ground nut | `ifct:H012` | 30 |
| Bengal gram, dal | `ifct:B001` | 15 |
| Black gram, dal | `ifct:B003` | 12 |
| Chillies, red | `ifct:G022` | 10 |
| Salt | `manual:salt` | 10 |
| Jaggery, cane | `ifct:I001` | 10 |
| Coriander seeds | `ifct:G024` | 6 |
| Curry leaves | `ifct:G010` | 6 |
| Mustard seeds | `ifct:H013` | 5 |
| Fenugreek seeds | `ifct:G026` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Coconut rice (thengai sadam) — `si:coconut_rice`
Slots: lunch, evening snack · Vegetarian · Serves 4 · Yield **1.95** · Raw 474 g → 924 g
Measures: **1 cup = 230 g**
Basis: roughly half a coconut (120 g grated) to 250 g raw rice.

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled | `ifct:A015` | 250 |
| Coconut, kernel, fresh | `ifct:H007` | 120 |
| Coconut oil | `ifct:T001` | 30 |
| Cashew nut | `ifct:H005` | 20 |
| Black gram, dal | `ifct:B003` | 12 |
| Bengal gram, dal | `ifct:B001` | 12 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Chillies, red | `ifct:G022` | 6 |
| Salt | `manual:salt` | 6 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Asafoetida | `ifct:G019` | 1 |

---

# 3. Kuzhambu, sambar and rasam

These have the largest yield factors in the set because they are mostly added water.
The absolute nutrient totals are driven by the dal, oil and tamarind; the yield factor
just spreads them over the final volume. If your rasam is thinner or thicker than mine,
the per-cup numbers move — please sanity-check the yield factors against your own pot.

### Sambar — `si:sambar`
Slots: lunch, dinner · Vegetarian · Serves 7 · Yield **2.15** · Raw 701 g → 1507 g
Measures: **1 cup = 200 g** · 1 ladle = 100 g
Basis: 150 g toor dal, mixed vegetables, tamarind, and the sambar-powder spices listed
inline (see conventions). Yield 2.15 reflects ~1.2 L of water going in and some boiling off.

| Ingredient | Code | Raw g |
|---|---|---:|
| Red gram, dal (toor) | `ifct:B021` | 150 |
| Drumstick | `ifct:D046` | 100 |
| Onion, small (shallot) | `ifct:G018` | 100 |
| Tomato, ripe, hybrid | `ifct:D075` | 100 |
| Brinjal - all varieties | `ifct:D031` | 80 |
| Carrot, orange | `ifct:F002` | 60 |
| Tamarind, pulp | `ifct:E064` | 30 |
| Gingelly oil | `ifct:T004` | 20 |
| Coriander seeds | `ifct:G024` | 12 |
| Chillies, red | `ifct:G022` | 10 |
| Salt | `manual:salt` | 10 |
| Coriander leaves | `ifct:G009` | 8 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Bengal gram, dal | `ifct:B001` | 4 |
| Cumin seeds | `ifct:G025` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Fenugreek seeds | `ifct:G026` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Tomato rasam — `si:rasam_tomato`
Slots: lunch, dinner · Vegetarian · Serves 6 · Yield **3.30** · Raw 365 g → 1205 g
Measures: **1 cup = 200 g** · 1 ladle = 100 g
Basis: 250 g tomato, a small ball of tamarind, thin dal water. Very high yield — rasam
is a drinkable consistency.

| Ingredient | Code | Raw g |
|---|---|---:|
| Tomato, ripe, hybrid | `ifct:D075` | 250 |
| Red gram, dal | `ifct:B021` | 30 |
| Tamarind, pulp | `ifct:E064` | 20 |
| Coriander leaves | `ifct:G009` | 10 |
| Ghee | `ifct:T013` | 10 |
| Garlic, big cloves | `ifct:G011` | 8 |
| Salt | `manual:salt` | 8 |
| Cumin seeds | `ifct:G025` | 5 |
| Curry leaves | `ifct:G010` | 5 |
| Coriander seeds | `ifct:G024` | 5 |
| Pepper, black | `ifct:G031` | 4 |
| Chillies, red | `ifct:G022` | 4 |
| Mustard seeds | `ifct:H013` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Pepper rasam (milagu rasam) — `si:rasam_pepper`
Slots: lunch, dinner · Vegetarian · Serves 6 · Yield **5.75** · Raw 191 g → 1098 g
Measures: **1 cup = 180 g**
Basis: the medicinal version — heavy on pepper and cumin, very little solid matter.
Yield 5.75 is the highest in the set and is entirely added water; reviewed and kept.

| Ingredient | Code | Raw g |
|---|---|---:|
| Tomato, ripe, hybrid | `ifct:D075` | 80 |
| Tamarind, pulp | `ifct:E064` | 25 |
| Red gram, dal | `ifct:B021` | 25 |
| Garlic, big cloves | `ifct:G011` | 10 |
| Ghee | `ifct:T013` | 10 |
| Pepper, black | `ifct:G031` | 8 |
| Coriander leaves | `ifct:G009` | 8 |
| Salt | `manual:salt` | 8 |
| Cumin seeds | `ifct:G025` | 6 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Lemon rasam — `si:rasam_lemon`
Slots: lunch, dinner · Vegetarian · Serves 6 · Yield **4.45** · Raw 247 g → 1099 g
Measures: **1 cup = 180 g**
Basis: no tamarind — juice of 2 limes added off the heat.

| Ingredient | Code | Raw g |
|---|---|---:|
| Tomato, ripe, hybrid | `ifct:D075` | 100 |
| Lemon, juice | `ifct:E033` | 45 |
| Red gram, dal | `ifct:B021` | 40 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Coriander leaves | `ifct:G009` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Salt | `manual:salt` | 8 |
| Ghee | `ifct:T013` | 8 |
| Cumin seeds | `ifct:G025` | 4 |
| Curry leaves | `ifct:G010` | 5 |
| Pepper, black | `ifct:G031` | 3 |
| Mustard seeds | `ifct:H013` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### More kuzhambu — `si:more_kuzhambu`
Slots: lunch · Vegetarian · Serves 6 · Yield **1.30** · Raw 900 g → 1170 g
Measures: **1 cup = 195 g**
Basis: 500 g curd as the base, ash gourd as the vegetable, ground coconut-cumin-dal paste.
Low yield because curd is the liquid — little extra water is added.

| Ingredient | Code | Raw g |
|---|---|---:|
| Curd, whole cow milk | `usda:curd` | 500 |
| Ash gourd | `ifct:D001` | 250 |
| Coconut, kernel, fresh | `ifct:H007` | 60 |
| Red gram, dal | `ifct:B021` | 20 |
| Coconut oil | `ifct:T001` | 15 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Bengal gram, dal | `ifct:B001` | 10 |
| Salt | `manual:salt` | 8 |
| Ginger, fresh | `ifct:G014` | 6 |
| Cumin seeds | `ifct:G025` | 5 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Turmeric powder | `ifct:G033` | 2 |
| Fenugreek seeds | `ifct:G026` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Vatha kuzhambu (vengaya) — `si:vatha_kuzhambu`
Slots: lunch · Vegetarian · Serves 12 (ladles) · Yield **2.15** · Raw 438 g → 942 g
Measures: **1 ladle = 80 g** · 1 cup = 160 g
Basis: **small-onion version**, because the sun-dried vathal (sundakkai / manathakkali)
that names the dish is not in IFCT — see resolutions A. Tamarind-forward and reduced thick, so it
is served in small quantities; the default measure is deliberately 80 g, not a full cup.

| Ingredient | Code | Raw g |
|---|---|---:|
| Onion, small (shallot) | `ifct:G018` | 150 |
| Drumstick | `ifct:D046` | 80 |
| Tamarind, pulp | `ifct:E064` | 60 |
| Gingelly oil | `ifct:T004` | 60 |
| Garlic, big cloves | `ifct:G011` | 15 |
| Coriander seeds | `ifct:G024` | 12 |
| Chillies, red | `ifct:G022` | 12 |
| Red gram, dal | `ifct:B021` | 10 |
| Jaggery, cane | `ifct:I001` | 10 |
| Salt | `manual:salt` | 10 |
| Curry leaves | `ifct:G010` | 6 |
| Mustard seeds | `ifct:H013` | 5 |
| Fenugreek seeds | `ifct:G026` | 4 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 2 |

### Kara kuzhambu — `si:kara_kuzhambu`
Slots: lunch, dinner · Vegetarian · Serves 6 · Yield **2.00** · Raw 629 g → 1258 g
Measures: **1 cup = 200 g**
Basis: brinjal-and-drumstick version with ground coconut, less reduced than vatha kuzhambu.

| Ingredient | Code | Raw g |
|---|---|---:|
| Brinjal - all varieties | `ifct:D031` | 150 |
| Onion, small (shallot) | `ifct:G018` | 120 |
| Drumstick | `ifct:D046` | 80 |
| Tomato, ripe, hybrid | `ifct:D075` | 80 |
| Tamarind, pulp | `ifct:E064` | 50 |
| Gingelly oil | `ifct:T004` | 45 |
| Coconut, kernel, fresh | `ifct:H007` | 40 |
| Garlic, big cloves | `ifct:G011` | 15 |
| Coriander seeds | `ifct:G024` | 12 |
| Chillies, red | `ifct:G022` | 10 |
| Salt | `manual:salt` | 10 |
| Curry leaves | `ifct:G010` | 6 |
| Mustard seeds | `ifct:H013` | 5 |
| Fenugreek seeds | `ifct:G026` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

---

# 4. Vegetable sides

All the dry sautés sit **below 1.0** — this is where water genuinely leaves the food.
Cabbage loses the most (0.75), carrot the least (0.88).

### Beans poriyal — `si:poriyal_beans`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **0.85** · Raw 506 g → 430 g
Measures: **1 serving = 110 g** · 1 cup = 130 g

| Ingredient | Code | Raw g |
|---|---|---:|
| French beans, hybrid | `ifct:D050` | 400 |
| Coconut, kernel, fresh | `ifct:H007` | 50 |
| Coconut oil | `ifct:T001` | 18 |
| Bengal gram, dal | `ifct:B001` | 8 |
| Black gram, dal | `ifct:B003` | 8 |
| Chillies, green-1 | `ifct:G001` | 6 |
| Salt | `manual:salt` | 3 |
| Mustard seeds | `ifct:H013` | 4 |
| Chillies, red | `ifct:G022` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Asafoetida | `ifct:G019` | 1 |

### Cabbage poriyal — `si:poriyal_cabbage`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **0.75** · Raw 552 g → 414 g
Measures: **1 serving = 105 g**
Basis: lowest yield of the poriyals — cabbage is ~92% water and collapses.

| Ingredient | Code | Raw g |
|---|---|---:|
| Cabbage, green | `ifct:C015` | 450 |
| Coconut, kernel, fresh | `ifct:H007` | 50 |
| Coconut oil | `ifct:T001` | 16 |
| Bengal gram, dal | `ifct:B001` | 8 |
| Black gram, dal | `ifct:B003` | 8 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Salt | `manual:salt` | 3 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Asafoetida | `ifct:G019` | 1 |

### Carrot poriyal — `si:poriyal_carrot`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **0.88** · Raw 499 g → 439 g
Measures: **1 serving = 110 g**

| Ingredient | Code | Raw g |
|---|---|---:|
| Carrot, orange | `ifct:F002` | 400 |
| Coconut, kernel, fresh | `ifct:H007` | 50 |
| Coconut oil | `ifct:T001` | 16 |
| Bengal gram, dal | `ifct:B001` | 8 |
| Black gram, dal | `ifct:B003` | 8 |
| Chillies, green-1 | `ifct:G001` | 6 |
| Salt | `manual:salt` | 3 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |

### Kootu (bottle gourd, poricha) — `si:kootu`
Slots: lunch, dinner · Vegetarian · Serves 5 · Yield **1.60** · Raw 614 g → 982 g
Measures: **1 cup = 195 g**
Basis: vegetable simmered with moong dal and a ground coconut-cumin paste. Above 1.0
because the dal absorbs water even though the gourd loses some.

| Ingredient | Code | Raw g |
|---|---|---:|
| Bottle gourd, elongate, pale green | `ifct:D007` | 400 |
| Green gram, dal | `ifct:B010` | 100 |
| Coconut, kernel, fresh | `ifct:H007` | 60 |
| Coconut oil | `ifct:T001` | 15 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Salt | `manual:salt` | 6 |
| Black gram, dal | `ifct:B003` | 6 |
| Cumin seeds | `ifct:G025` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Pepper, black | `ifct:G031` | 3 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Avial — `si:avial`
Slots: lunch · Vegetarian · Serves 6 · Yield **1.15** · Raw 951 g → 1094 g
Measures: **1 cup = 180 g**
Basis: seven vegetables in roughly equal parts, thick coconut-cumin paste, finished with
raw coconut oil and curd. I used the **curd-soured** version (Tamil Nadu); the Kerala
version uses tamarind or raw mango instead — flagged.

| Ingredient | Code | Raw g |
|---|---|---:|
| Curd, whole cow milk | `usda:curd` | 150 |
| Coconut, kernel, fresh | `ifct:H007` | 120 |
| Drumstick | `ifct:D046` | 100 |
| Plantain, green | `ifct:D063` | 100 |
| Cho-cho-marrow (chow chow) | `ifct:D038` | 100 |
| Yam, elephant | `ifct:F017` | 100 |
| Carrot, orange | `ifct:F002` | 80 |
| Pumpkin, green, cylindrical | `ifct:D065` | 80 |
| Broad beans | `ifct:D032` | 60 |
| Coconut oil | `ifct:T001` | 25 |
| Chillies, green-1 | `ifct:G001` | 15 |
| Salt | `manual:salt` | 8 |
| Cumin seeds | `ifct:G025` | 6 |
| Curry leaves | `ifct:G010` | 5 |
| Turmeric powder | `ifct:G033` | 2 |

### Cabbage thoran — `si:thoran`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **0.80** · Raw 571 g → 457 g
Measures: **1 serving = 115 g**
Basis: **Kerala** dish, included as the brief asked. Differs from cabbage poriyal by
using more coconut, crushed garlic and cumin, and no dal tempering.

| Ingredient | Code | Raw g |
|---|---|---:|
| Cabbage, green | `ifct:C015` | 400 |
| Coconut, kernel, fresh | `ifct:H007` | 80 |
| Onion, small (shallot) | `ifct:G018` | 40 |
| Coconut oil | `ifct:T001` | 18 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Garlic, small cloves | `ifct:G012` | 6 |
| Salt | `manual:salt` | 3 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Cumin seeds | `ifct:G025` | 3 |
| Turmeric powder | `ifct:G033` | 2 |

### Keerai masiyal — `si:keerai_masiyal`
Slots: lunch, dinner · Vegetarian · Serves 4 · Yield **1.10** · Raw 541 g → 595 g
Measures: **1 serving = 150 g**
Basis: amaranth greens boiled with moong dal and mashed. The greens collapse to about a
third of their raw weight, but the dal swells and the cooking water is kept in — net 1.10.

| Ingredient | Code | Raw g |
|---|---|---:|
| Amaranth leaves, green | `ifct:C002` | 400 |
| Green gram, dal | `ifct:B010` | 60 |
| Onion, small (shallot) | `ifct:G018` | 40 |
| Gingelly oil | `ifct:T004` | 12 |
| Garlic, big cloves | `ifct:G011` | 10 |
| Chillies, red | `ifct:G022` | 5 |
| Salt | `manual:salt` | 5 |
| Cumin seeds | `ifct:G025` | 4 |
| Mustard seeds | `ifct:H013` | 4 |
| Asafoetida | `ifct:G019` | 1 |

### Vegetable kurma — `si:kurma`
Slots: breakfast, lunch, dinner · Vegetarian · Serves 5 · Yield **1.25** · Raw 923 g → 1154 g
Measures: **1 cup = 230 g**
Basis: the standard accompaniment to idiyappam, appam and parotta. Ground coconut-cashew-
poppy paste. Note: cinnamon, bay leaf and fennel are absent from IFCT and are omitted.

| Ingredient | Code | Raw g |
|---|---|---:|
| Potato, brown skin, big | `ifct:F006` | 200 |
| Carrot, orange | `ifct:F002` | 120 |
| Onion, big | `ifct:G017` | 120 |
| French beans, hybrid | `ifct:D050` | 100 |
| Tomato, ripe, hybrid | `ifct:D075` | 100 |
| Peas, fresh | `ifct:D061` | 80 |
| Coconut, kernel, fresh | `ifct:H007` | 80 |
| Sunflower oil | `ifct:T012` | 35 |
| Cashew nut | `ifct:H005` | 15 |
| Garlic, big cloves | `ifct:G011` | 12 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Ginger, fresh | `ifct:G014` | 10 |
| Mint leaves | `ifct:G016` | 10 |
| Coriander leaves | `ifct:G009` | 10 |
| Salt | `manual:salt` | 8 |
| Poppy seeds | `ifct:G032` | 6 |
| Turmeric powder | `ifct:G033` | 2 |
| Cardamom, green | `ifct:G020` | 2 |
| Cloves | `ifct:G023` | 1 |

### Chana sundal — `si:sundal_chana`
Slots: evening snack · Vegetarian · Serves 5 · Yield **1.95** · Raw 303 g → 591 g
Measures: **1 cup = 120 g**
Basis: dried whole Bengal gram soaked overnight and boiled — roughly 2.5× its dry weight —
then tossed with coconut and a tempering.

| Ingredient | Code | Raw g |
|---|---|---:|
| Bengal gram, whole | `ifct:B002` | 200 |
| Coconut, kernel, fresh | `ifct:H007` | 60 |
| Coconut oil | `ifct:T001` | 12 |
| Black gram, dal | `ifct:B003` | 6 |
| Chillies, green-1 | `ifct:G001` | 6 |
| Chillies, red | `ifct:G022` | 5 |
| Salt | `manual:salt` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Asafoetida | `ifct:G019` | 1 |

### Pattani (dried pea) sundal — `si:sundal_pattani`
Slots: evening snack · Vegetarian · Serves 5 · Yield **1.95** · Raw 308 g → 601 g
Measures: **1 cup = 120 g**

| Ingredient | Code | Raw g |
|---|---|---:|
| Peas, dry | `ifct:B017` | 200 |
| Coconut, kernel, fresh | `ifct:H007` | 60 |
| Coconut oil | `ifct:T001` | 12 |
| Black gram, dal | `ifct:B003` | 6 |
| Chillies, green-1 | `ifct:G001` | 6 |
| Chillies, red | `ifct:G022` | 5 |
| Salt | `manual:salt` | 5 |
| Ginger, fresh | `ifct:G014` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Asafoetida | `ifct:G019` | 1 |

---

# 5. Non-vegetarian

> **Fish is a VARIANT SET, not one species (decision 4).** You pick the fish when you
> log, and the planner has to be able to offer the fish you actually bought. IFCT's 91
> marine fish are not interchangeable — per 100 g raw, nethili carries 0.78 g fat and
> mathi 8.99 g, an elevenfold spread that moves the calories and omega-3 for the whole
> meal. So each fish dish ships in four species, sharing a display prefix so they group
> in a picker, with **every non-fish ingredient identical across the four**:
>
> | Species | Code | Protein g | Fat g | Why it is here |
> |---|---|---:|---:|---|
> | Vanjaram (seer) | `ifct:P087` | 22.28 | 5.18 | the prestige kuzhambu fish |
> | Sardine (mathi) | `ifct:P071` | 17.91 | 8.99 | the everyday cheap fish, and the fattiest |
> | Mackerel (ayila) | `ifct:P034` | 21.51 | 1.53 | the other everyday staple |
> | Nethili (anchovy) | `ifct:P003` | 19.88 | 0.78 | small fry, fried whole, the leanest |
>
> Between them they span the fat range end to end, which is exactly what makes the
> choice worth offering rather than averaging away.

### Fish kuzhambu (meen kuzhambu) — `si:fish_kuzhambu_vanjaram` · `_sardine` · `_mackerel` · `_nethili`
Slots: lunch, dinner · **Fishetarian** · Serves 5 · Yield **1.50** · Raw 863 g → 1295 g
Measures: **1 serving = 260 g** · 1 ladle gravy = 100 g
Basis: the Tamil Nadu style — tamarind-heavy, gingelly oil, no coconut. Four dishes,
identical apart from the fish row.

| Ingredient | Code | Raw g |
|---|---|---:|
| **Fish** (one of the four above) | `ifct:P087` / `P071` / `P034` / `P003` | 500 |
| Onion, small (shallot) | `ifct:G018` | 100 |
| Tomato, ripe, hybrid | `ifct:D075` | 100 |
| Tamarind, pulp | `ifct:E064` | 50 |
| Gingelly oil | `ifct:T004` | 45 |
| Coriander seeds | `ifct:G024` | 15 |
| Garlic, big cloves | `ifct:G011` | 15 |
| Chillies, red | `ifct:G022` | 12 |
| Salt | `manual:salt` | 10 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 4 |
| Fenugreek seeds | `ifct:G026` | 3 |
| Turmeric powder | `ifct:G033` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Fish fry — `si:fish_fry_vanjaram` · `_sardine` · `_mackerel` · `_nethili`
Slots: lunch, dinner · **Fishetarian** · Serves 4 · Yield **0.80** · Raw 494 g → 395 g
Measures: **1 piece = 100 g**
Basis: masala-coated and shallow fried. Sub-1.0 because frying drives off water faster
than the fish takes up oil. **Deep-fry oil retention: 40 g of the 395 g finished weight
is absorbed oil, i.e. 10%** — the lowest in the set, because the masala coat is thin and
the fish sheds water fast. Four dishes, identical apart from the fish row.

| Ingredient | Code | Raw g |
|---|---|---:|
| **Fish** (one of the four above) | `ifct:P087` / `P071` / `P034` / `P003` | 400 |
| Groundnut oil *(absorbed, 10%)* | `ifct:T005` | 40 |
| Rice, raw, milled *(as rice flour coating)* | `ifct:A015` | 20 |
| Garlic, big cloves | `ifct:G011` | 10 |
| Chillies, red | `ifct:G022` | 8 |
| Ginger, fresh | `ifct:G014` | 8 |
| Salt | `manual:salt` | 4.5 |
| Turmeric powder | `ifct:G033` | 3 |

### Chicken curry — `si:chicken_curry`
Slots: lunch, dinner · **Non-veg** · Serves 5 · Yield **1.10** · Raw 1169 g → 1286 g
Measures: **1 serving = 255 g**
Basis: home Chettinad-leaning masala with ground coconut and poppy seed. Chicken entered
as skinless leg. Cinnamon, bay leaf, star anise and fennel are absent from IFCT and omitted.

| Ingredient | Code | Raw g |
|---|---|---:|
| Chicken, poultry, leg, skinless | `ifct:N001` | 600 |
| Onion, big | `ifct:G017` | 200 |
| Tomato, ripe, hybrid | `ifct:D075` | 150 |
| Coconut, kernel, fresh | `ifct:H007` | 60 |
| Groundnut oil | `ifct:T005` | 45 |
| Garlic, big cloves | `ifct:G011` | 20 |
| Ginger, fresh | `ifct:G014` | 20 |
| Coriander seeds | `ifct:G024` | 15 |
| Chillies, red | `ifct:G022` | 12 |
| Salt | `manual:salt` | 10 |
| Coriander leaves | `ifct:G009` | 10 |
| Curry leaves | `ifct:G010` | 6 |
| Cumin seeds | `ifct:G025` | 5 |
| Pepper, black | `ifct:G031` | 5 |
| Poppy seeds | `ifct:G032` | 5 |
| Turmeric powder | `ifct:G033` | 3 |
| Cardamom, green | `ifct:G020` | 2 |
| Cloves | `ifct:G023` | 1 |

### Egg curry (muttai kuzhambu) — `si:egg_curry`
Slots: lunch, dinner · **Eggetarian** · Serves 4 · Yield **1.40** · Raw 646 g → 904 g
Measures: **1 serving (1 egg + gravy) = 225 g**
Basis: 4 eggs (200 g edible portion) boiled and simmered in an onion-tomato-coconut gravy.

| Ingredient | Code | Raw g |
|---|---|---:|
| Egg, poultry, whole, raw | `ifct:M001` | 200 |
| Onion, big | `ifct:G017` | 150 |
| Tomato, ripe, hybrid | `ifct:D075` | 150 |
| Coconut, kernel, fresh | `ifct:H007` | 50 |
| Groundnut oil | `ifct:T005` | 30 |
| Garlic, big cloves | `ifct:G011` | 12 |
| Ginger, fresh | `ifct:G014` | 10 |
| Coriander seeds | `ifct:G024` | 10 |
| Chillies, red | `ifct:G022` | 8 |
| Salt | `manual:salt` | 8 |
| Coriander leaves | `ifct:G009` | 8 |
| Curry leaves | `ifct:G010` | 5 |
| Mustard seeds | `ifct:H013` | 3 |
| Turmeric powder | `ifct:G033` | 2 |

### Omelette — `si:omelette`
Slots: breakfast, evening snack, dinner · **Eggetarian** · Serves 1 · Yield **0.85** · Raw 149 g → 126 g
Measures: **1 omelette (2 eggs) = 126 g**
Basis: built from raw egg plus oil rather than IFCT's ready-made `M007 Egg, poultry, omlet`,
so the oil is explicit and adjustable. Sub-1.0 because egg loses water in the pan.

| Ingredient | Code | Raw g |
|---|---|---:|
| Egg, poultry, whole, raw | `ifct:M001` | 100 |
| Onion, big | `ifct:G017` | 30 |
| Sunflower oil | `ifct:T012` | 8 |
| Chillies, green-1 | `ifct:G001` | 5 |
| Coriander leaves | `ifct:G009` | 4 |
| Salt | `manual:salt` | 0.8 |
| Pepper, black | `ifct:G031` | 1 |

### Boiled egg — `si:egg_boiled`
Slots: breakfast, mid-morning snack, evening snack · **Eggetarian** · Serves 2 · Yield **1.00** · Raw 100 g → 100 g
Measures: **1 egg = 50 g**
Basis: edible portion only, shell excluded. Boiling changes weight negligibly.

| Ingredient | Code | Raw g |
|---|---|---:|
| Egg, poultry, whole, raw | `ifct:M001` | 100 |

---

# 6. Chutneys and podis

### Coconut chutney — `si:chutney_coconut`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 12 (2-tbsp portions) · Yield **1.80** · Raw 275 g → 495 g
Measures: **2 tbsp = 40 g** · 1 serving = 80 g
Basis: about half a coconut, ground with water to a spoonable consistency — the water is
why yield is 1.80. Roasted gram (pottukadalai) is not in IFCT; Bengal gram dal used instead.

| Ingredient | Code | Raw g |
|---|---|---:|
| Coconut, kernel, fresh | `ifct:H007` | 200 |
| Bengal gram, dal *(for roasted gram)* | `ifct:B001` | 30 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Coconut oil | `ifct:T001` | 10 |
| Ginger, fresh | `ifct:G014` | 6 |
| Salt | `manual:salt` | 4 |
| Black gram, dal | `ifct:B003` | 4 |
| Mustard seeds | `ifct:H013` | 3 |
| Chillies, red | `ifct:G022` | 3 |
| Curry leaves | `ifct:G010` | 3 |

### Tomato chutney — `si:chutney_tomato`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 11 (2-tbsp portions) · Yield **0.82** · Raw 527 g → 432 g
Measures: **2 tbsp = 40 g** · 1 serving = 70 g
Basis: tomatoes sautéed down before grinding — no water added, so it reduces below 1.0.

| Ingredient | Code | Raw g |
|---|---|---:|
| Tomato, ripe, hybrid | `ifct:D075` | 350 |
| Onion, big | `ifct:G017` | 100 |
| Gingelly oil | `ifct:T004` | 25 |
| Black gram, dal | `ifct:B003` | 12 |
| Bengal gram, dal | `ifct:B001` | 12 |
| Chillies, red | `ifct:G022` | 8 |
| Tamarind, pulp | `ifct:E064` | 8 |
| Salt | `manual:salt` | 5 |
| Mustard seeds | `ifct:H013` | 3 |
| Curry leaves | `ifct:G010` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Coriander chutney — `si:chutney_coriander`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 12 (2-tbsp portions) · Yield **1.55** · Raw 273 g → 423 g
Measures: **2 tbsp = 35 g** · 1 serving = 70 g
Basis: two large bunches of coriander (120 g leaves, stalks discarded).

| Ingredient | Code | Raw g |
|---|---|---:|
| Coriander leaves | `ifct:G009` | 120 |
| Coconut, kernel, fresh | `ifct:H007` | 80 |
| Black gram, dal | `ifct:B003` | 15 |
| Bengal gram, dal | `ifct:B001` | 15 |
| Gingelly oil | `ifct:T004` | 15 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Tamarind, pulp | `ifct:E064` | 8 |
| Salt | `manual:salt` | 4 |
| Mustard seeds | `ifct:H013` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Mint chutney — `si:chutney_mint`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 13 (2-tbsp portions) · Yield **1.45** · Raw 307 g → 445 g
Measures: **2 tbsp = 35 g** · 1 serving = 75 g

| Ingredient | Code | Raw g |
|---|---|---:|
| Mint leaves | `ifct:G016` | 100 |
| Coconut, kernel, fresh | `ifct:H007` | 80 |
| Onion, big | `ifct:G017` | 40 |
| Coriander leaves | `ifct:G009` | 30 |
| Black gram, dal | `ifct:B003` | 15 |
| Gingelly oil | `ifct:T004` | 15 |
| Chillies, green-1 | `ifct:G001` | 12 |
| Tamarind, pulp | `ifct:E064` | 8 |
| Salt | `manual:salt` | 4 |
| Mustard seeds | `ifct:H013` | 3 |

### Onion chutney (vengaya chutney) — `si:chutney_onion`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 6 · Yield **0.84** · Raw 309 g → 260 g
Measures: **2 tbsp = 40 g**
Basis: shallots sautéed till soft, ground thick. Reduces like tomato chutney.

| Ingredient | Code | Raw g |
|---|---|---:|
| Onion, small (shallot) | `ifct:G018` | 250 |
| Gingelly oil | `ifct:T004` | 25 |
| Black gram, dal | `ifct:B003` | 12 |
| Tamarind, pulp | `ifct:E064` | 10 |
| Chillies, red | `ifct:G022` | 8 |
| Salt | `manual:salt` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Sambar powder — `si:sambar_powder`
Slots: lunch, dinner · Vegetarian · Serves 140 (tsp) · Yield **0.92** · Raw 610 g → 561 g
Measures: **1 tsp = 4 g** · 1 tbsp = 12 g
Basis: a standard Tamil Nadu home blend, dry-roasted and ground. Yield below 1.0 is
moisture driven off during roasting (~8%). "Serves 45" means one batch is about 45
family-sized uses at ~12 g each; it is a store-cupboard item, not a meal.

| Ingredient | Code | Raw g |
|---|---|---:|
| Coriander seeds | `ifct:G024` | 250 |
| Chillies, red | `ifct:G022` | 150 |
| Red gram, dal | `ifct:B021` | 50 |
| Bengal gram, dal | `ifct:B001` | 50 |
| Turmeric powder | `ifct:G033` | 30 |
| Cumin seeds | `ifct:G025` | 25 |
| Fenugreek seeds | `ifct:G026` | 20 |
| Pepper, black | `ifct:G031` | 20 |
| Curry leaves | `ifct:G010` | 10 |
| Asafoetida | `ifct:G019` | 5 |

### Rasam powder — `si:rasam_powder`
Slots: lunch, dinner · Vegetarian · Serves 105 (tsp) · Yield **0.92** · Raw 455 g → 419 g
Measures: **1 tsp = 4 g** · 1 tbsp = 12 g
Basis: pepper- and cumin-forward, far less chilli than sambar powder.

| Ingredient | Code | Raw g |
|---|---|---:|
| Coriander seeds | `ifct:G024` | 200 |
| Pepper, black | `ifct:G031` | 60 |
| Cumin seeds | `ifct:G025` | 60 |
| Chillies, red | `ifct:G022` | 60 |
| Red gram, dal | `ifct:B021` | 40 |
| Turmeric powder | `ifct:G033` | 15 |
| Fenugreek seeds | `ifct:G026` | 10 |
| Curry leaves | `ifct:G010` | 10 |

### Idli podi (milagai podi) — `si:idli_podi`
Slots: breakfast, evening snack, dinner · Vegetarian · Serves 68 (tsp) · Yield **0.93** · Raw 365 g → 339 g
Measures: **1 tsp = 5 g** · 1 tbsp = 15 g
Basis: dal-heavy version. Usually eaten mixed with gingelly oil at the plate — that oil is
*not* included here, since the amount is per-person. Log the oil separately.

| Ingredient | Code | Raw g |
|---|---|---:|
| Black gram, dal | `ifct:B003` | 150 |
| Bengal gram, dal | `ifct:B001` | 100 |
| Chillies, red | `ifct:G022` | 60 |
| Gingelly seeds, white | `ifct:H011` | 30 |
| Salt | `manual:salt` | 12 |
| Gingelly oil | `ifct:T004` | 10 |
| Asafoetida | `ifct:G019` | 3 |

---

# 7. Fried snacks

**Oil in this section is the oil absorbed by the food, not the oil in the kadai.**
Percentages of finished weight are stated per dish. These are the least certain numbers
in the whole document — see resolutions B1.

### Medu vada — `si:medu_vada`
Slots: breakfast, evening snack · Vegetarian · Serves 12 (vadas) · Yield **1.30** · Raw 411 g → 534 g
Measures: **1 vada = 45 g** · 2 vada = 90 g
Basis: 250 g urad dal makes 12 vadas. Oil absorption assumed 11% of finished weight (60 g).
Above 1.0 because the ground batter holds water even after frying.

| Ingredient | Code | Raw g |
|---|---|---:|
| Black gram, dal | `ifct:B003` | 250 |
| Onion, big | `ifct:G017` | 60 |
| Groundnut oil *(absorbed)* | `ifct:T005` | 60 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Coriander leaves | `ifct:G009` | 6 |
| Salt | `manual:salt` | 6 |
| Curry leaves | `ifct:G010` | 5 |
| Pepper, black | `ifct:G031` | 3 |
| Cumin seeds | `ifct:G025` | 3 |

### Masala vada (paruppu vadai) — `si:masala_vada`
Slots: evening snack · Vegetarian · Serves 12 (vadas) · Yield **1.02** · Raw 492 g → 502 g
Measures: **1 vada = 42 g** · 2 vada = 84 g
Basis: coarsely ground soaked channa dal, 12 vadas. Yield ≈1.0: coarse dal holds less water
than the fine urad batter, and frying dries it out. Oil absorption 13% (65 g).

| Ingredient | Code | Raw g |
|---|---|---:|
| Bengal gram, dal | `ifct:B001` | 250 |
| Onion, big | `ifct:G017` | 80 |
| Groundnut oil *(absorbed)* | `ifct:T005` | 65 |
| Red gram, dal | `ifct:B021` | 50 |
| Chillies, red | `ifct:G022` | 10 |
| Chillies, green-1 | `ifct:G001` | 8 |
| Coriander leaves | `ifct:G009` | 8 |
| Ginger, fresh | `ifct:G014` | 6 |
| Curry leaves | `ifct:G010` | 6 |
| Salt | `manual:salt` | 6 |
| Fenugreek seeds | `ifct:G026` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Bonda (aloo bonda) — `si:bonda`
Slots: evening snack · Vegetarian · Serves 10 (bondas) · Yield **0.90** · Raw 767 g → 690 g
Measures: **1 bonda = 70 g** · 2 bonda = 140 g
Basis: 10 bondas. Sub-1.0 because the potato filling is already cooked and the thin batter
shell loses its water in the oil. Besan is not in IFCT; Bengal gram dal used. Oil 11% (75 g).

| Ingredient | Code | Raw g |
|---|---|---:|
| Potato, brown skin, big | `ifct:F006` | 400 |
| Bengal gram, dal *(for besan)* | `ifct:B001` | 150 |
| Onion, big | `ifct:G017` | 100 |
| Groundnut oil *(absorbed)* | `ifct:T005` | 75 |
| Chillies, green-1 | `ifct:G001` | 10 |
| Ginger, fresh | `ifct:G014` | 8 |
| Coriander leaves | `ifct:G009` | 8 |
| Salt | `manual:salt` | 6 |
| Mustard seeds | `ifct:H013` | 4 |
| Curry leaves | `ifct:G010` | 4 |
| Turmeric powder | `ifct:G033` | 2 |

### Bajji (plantain) — `si:bajji`
Slots: evening snack · Vegetarian · Serves 12 (bajjis) · Yield **0.90** · Raw 564 g → 508 g
Measures: **1 bajji = 42 g** · 3 bajji = 126 g
Basis: 12 slices. Oil absorption assumed 18% of finished weight (90 g) — bajji batter is
the thirstiest in this section. Besan and rice flour substituted (see resolutions A). **Cooking soda
is omitted because IFCT has no entry for it — this understates sodium slightly.**

| Ingredient | Code | Raw g |
|---|---|---:|
| Plantain, green | `ifct:D063` | 250 |
| Bengal gram, dal *(for besan)* | `ifct:B001` | 180 |
| Groundnut oil *(absorbed)* | `ifct:T005` | 90 |
| Rice, raw, milled *(as rice flour)* | `ifct:A015` | 30 |
| Chillies, red | `ifct:G022` | 6 |
| Salt | `manual:salt` | 5 |
| Turmeric powder | `ifct:G033` | 2 |
| Asafoetida | `ifct:G019` | 1 |

### Murukku (thenkuzhal) — `si:murukku`
Slots: evening snack · Vegetarian · Serves 24 (pieces) · Yield **0.95** · Raw 640 g → 608 g
Measures: **1 murukku = 25 g** · 2 murukku = 50 g
Basis: 4:1 rice flour to urad flour, the thenkuzhal ratio. ~24 pieces. Sub-1.0 because the
finished murukku is dry and crisp — nearly all the dough water is driven off. Oil 15% (90 g).

| Ingredient | Code | Raw g |
|---|---|---:|
| Rice, raw, milled *(as rice flour)* | `ifct:A015` | 400 |
| Black gram, dal *(as urad flour)* | `ifct:B003` | 100 |
| Groundnut oil *(absorbed)* | `ifct:T005` | 90 |
| Ghee | `ifct:T013` | 25 |
| Gingelly seeds, white | `ifct:H011` | 10 |
| Salt | `manual:salt` | 7 |
| Cumin seeds | `ifct:G025` | 6 |
| Asafoetida | `ifct:G019` | 2 |

---

# 8. Drinks

> **Coffee and tea are built from brewed LIQUID (decision 5).** The draft listed 24 g of
> coffee powder as an ingredient, which credits the cup with the protein, fat, fibre,
> magnesium and potassium of beans that are steeped and thrown away. Only the
> water-soluble extractives reach the tumbler. The four drinks below therefore reference
> `usda:coffee_brewed` and `usda:tea_brewed` — real USDA rows priced per 100 g of
> **liquid** — with milk and sugar as separate ingredients. Yield factor is **1.00** for
> all four: every ingredient is already a liquid at its final strength, so nothing is
> absorbed and nothing boils off.
>
> Known conservatism, stated so it is not invisible: the USDA rows are US drip strength
> (99.4 g water, 40 mg caffeine per 100 g). South Indian filter decoction is roughly
> three times stronger before it is cut with milk, so the coffee-derived micronutrients
> are understated by about that factor — of the order of 50 mg potassium per tumbler.
> Energy, fat and protein are unaffected, because brewed coffee is 99% water and the milk
> and sugar dominate every number the app acts on.

### Filter coffee, with sugar — `si:filter_coffee_sugar`
Slots: breakfast, mid-morning snack, evening snack · Vegetarian · Serves 4 · Yield **1.00** · Raw 632 g → 632 g
Measures: **1 tumbler (150 ml) = 158 g** · 1 small cup = 105 g
Basis: ~100 ml milk and ~50 ml decoction per tumbler, 2 tsp sugar. The tumbler weighs a
little over 150 g because dissolved sugar raises the density.

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 400 |
| Coffee, brewed | `usda:coffee_brewed` | 200 |
| Sugar | `manual:sugar` | 32 |

### Filter coffee, no sugar — `si:filter_coffee_plain`
Slots: breakfast, mid-morning snack, evening snack · Vegetarian · Serves 4 · Yield **1.00** · Raw 600 g → 600 g
Measures: **1 tumbler (150 ml) = 150 g** · 1 small cup = 100 g

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 400 |
| Coffee, brewed | `usda:coffee_brewed` | 200 |

### Tea, with sugar — `si:tea`
Slots: mid-morning snack, evening snack · Vegetarian · Serves 4 · Yield **1.00** · Raw 632 g → 632 g
Measures: **1 cup = 158 g**
Basis: less milk and more water than coffee — ~60 ml milk to ~90 ml brewed tea per cup,
the reverse of the filter coffee proportions.

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 240 |
| Tea, black, brewed | `usda:tea_brewed` | 360 |
| Sugar | `manual:sugar` | 32 |

### Tea, no sugar — `si:tea_no_sugar`
Slots: mid-morning snack, evening snack · Vegetarian · Serves 4 · Yield **1.00** · Raw 600 g → 600 g
Measures: **1 cup = 150 g**

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 240 |
| Tea, black, brewed | `usda:tea_brewed` | 360 |

### Neer mor (spiced buttermilk) — `si:neer_mor`
Slots: mid-morning snack, lunch, evening snack · Vegetarian · Serves 4 · Yield **3.70** · Raw 269 g → 995 g
Measures: **1 glass (250 ml) = 250 g**
Basis: 250 g curd diluted roughly 1:3 with water. **Built from curd rather than a separate
buttermilk ingredient** — the dilution is exactly what the yield factor expresses, so no
`manual:buttermilk` entry is needed (see resolutions A).

| Ingredient | Code | Raw g |
|---|---|---:|
| Curd, whole cow milk | `usda:curd` | 250 |
| Ginger, fresh | `ifct:G014` | 5 |
| Chillies, green-1 | `ifct:G001` | 4 |
| Salt | `manual:salt` | 3 |
| Curry leaves | `ifct:G010` | 3 |
| Coriander leaves | `ifct:G009` | 3 |
| Asafoetida | `ifct:G019` | 1 |

### Ragi kanji (sweet) — `si:ragi_kanji`
Slots: breakfast, mid-morning snack · Vegetarian · Serves 2 · Yield **1.85** · Raw 290 g → 537 g
Measures: **1 glass = 265 g**
Basis: 60 g ragi flour cooked into a slurry, finished with milk and jaggery.

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 200 |
| Ragi | `ifct:A010` | 60 |
| Jaggery, cane | `ifct:I001` | 30 |

### Curd (plain, as a side) — `si:curd_side`
Slots: lunch, dinner · Vegetarian · Serves 1 · Yield **1.00** · Raw 150 g → 150 g
Measures: **1 cup = 150 g** · ½ cup = 75 g
Basis: single-ingredient dish so the end-of-meal curd can be logged in one tap.

| Ingredient | Code | Raw g |
|---|---|---:|
| Curd, whole cow milk | `usda:curd` | 150 |

---

# 9. Sweets

### Semiya payasam — `si:payasam_semiya`
Slots: evening snack, lunch, dinner · Vegetarian · Serves 6 · Yield **1.05** · Raw 1092 g → 1147 g
Measures: **1 cup = 190 g**
Basis: milk-based. Yield barely above 1.0 — the vermicelli absorbs the milk rather than
added water, and some milk boils off.

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 800 |
| Sugar | `manual:sugar` | 120 |
| Wheat, vermicelli, roasted | `ifct:A024` | 100 |
| Ghee | `ifct:T013` | 25 |
| Cashew nut | `ifct:H005` | 25 |
| Raisins, dried, black | `ifct:E057` | 20 |
| Cardamom, green | `ifct:G020` | 2 |

### Paruppu payasam — `si:payasam_paruppu`
Slots: evening snack, lunch, dinner · Vegetarian · Serves 6 · Yield **1.50** · Raw 727 g → 1091 g
Measures: **1 cup = 180 g**
Basis: jaggery and coconut milk version. Coconut milk is entered as fresh coconut kernel,
which is how it is extracted at home — see resolutions A16, this overstates fibre.

| Ingredient | Code | Raw g |
|---|---|---:|
| Milk, whole, Cow | `ifct:L002` | 300 |
| Jaggery, cane | `ifct:I001` | 200 |
| Green gram, dal | `ifct:B010` | 100 |
| Coconut, kernel, fresh | `ifct:H007` | 80 |
| Ghee | `ifct:T013` | 25 |
| Cashew nut | `ifct:H005` | 20 |
| Cardamom, green | `ifct:G020` | 2 |

### Rava kesari — `si:kesari`
Slots: evening snack, breakfast · Vegetarian · Serves 8 · Yield **1.60** · Raw 592 g → 947 g
Measures: **1 piece = 120 g**
Basis: **ghee halved 100 g → 50 g (decision 2).** 1 : 1.5 : 0.5 rava : sugar : ghee is
the festival/restaurant ratio; the home version uses half the ghee, which takes about
55 kcal per piece off a dish that gets eaten at breakfast. Yield rises from 1.55 to 1.60
because the same water still goes into the rava on a smaller raw base.

| Ingredient | Code | Raw g |
|---|---|---:|
| Sugar | `manual:sugar` | 300 |
| Wheat, semolina | `ifct:A022` | 200 |
| Ghee | `ifct:T013` | 50 |
| Cashew nut | `ifct:H005` | 25 |
| Raisins, dried, black | `ifct:E057` | 15 |
| Cardamom, green | `ifct:G020` | 2 |

---
---

# Resolutions — what the review decided, and what is still uncertain

## A. Ingredients IFCT does not have

All 542 IFCT rows were re-checked. Two findings differed from the Task 3 codes brief;
both are now settled.

| # | Ingredient | Status | Resolution as coded |
|---|---|---|---|
| 1 | **Salt** | Genuinely absent | **CREATED as `manual:salt`.** Sodium 38,700 mg / 100 g from USDA Foundation fdc 746775 *Salt, table, iodized*, cross-checked against pure NaCl's 39.34% sodium by mass (Na 22.98977 / NaCl 58.44277, IUPAC standard atomic weights) — USDA's figure is 98.4% of that, which is what a real retail salt is once water and anticaking agent are counted. Iodine is **1,500 µg / 100 g**, the FSSAI Fortification of Foods Regulations 2018 retail minimum of 15 ppm, NOT USDA's 5,080 µg (the US ~50 ppm level). Used by **57 of the 72 dishes** — the task brief's estimate of 40 was low. |
| 2 | **Curd / dahi** | Genuinely absent (`L001`–`L004` are buffalo milk, cow milk, paneer, khoa) | **CREATED as `usda:curd`** from USDA Foundation fdc 2259793 *Yogurt, plain, whole milk* — an exact-name match, so no derivation from cow milk was needed. Seven nutrients the Foundation row does not carry (vitamin A, E, C, folate, B12, pantothenic acid, selenium) come from SR Legacy fdc 171284, the same food, tagged separately. **Iodine deliberately omitted**: US dairy iodine is iodophor sanitiser residue from US milking practice, the same reason `etl.load_usda` pairs cow milk for B12 only. |
| 3 | **White sugar** | Genuinely absent — the Sugars group has only `I001` jaggery and `I002` cane juice | **CREATED as `manual:sugar`** from USDA SR Legacy fdc 169655 *Sugars, granulated*: 99.98 g carbohydrate, 99.8 g of it free sugar, 387 kcal. (387, not the round 400 — sucrose's Atwater factor is 3.87 kcal/g.) The code keeps its `manual:` prefix; the data is entirely USDA and `Ingredient.source` says so. |
| 4 | **Coffee** | Powder absent | **CREATED as `usda:coffee_brewed`** from USDA SR Legacy fdc 171890 *Beverages, coffee, brewed, prepared with tap water*, per 100 g of LIQUID. The powder was never the right model — see decision 5 in the drinks section. |
| 5 | **Tea** | Leaves absent | **CREATED as `usda:tea_brewed`** from USDA SR Legacy fdc 173227 *Beverages, tea, black, brewed, prepared with tap water*, per 100 g of LIQUID. |
| 6 | **Tamarind pulp** | **PRESENT as `ifct:E064` "Tamarind, pulp"** | **No manual ingredient created.** The Task 3 codes brief said tamarind pulp was absent and proposed `manual:tamarind_pulp`; that was wrong. **14 dishes** use the real `ifct:E064` (11 recipes before the fish variants); the draft's count of nine was low. |
| 7 | **Buttermilk** | Absent, and **not needed** | **`manual:buttermilk` deliberately NOT created.** Neer mor is `usda:curd` plus dilution expressed through `yield_factor` 3.70 — that removes one hand-derived ingredient from the chain. |
| 8 | **Rice flour** | Absent | Uses `ifct:A015 Rice, raw, milled`. Rice flour *is* milled raw rice. Affects idiyappam, puttu, rava dosa, murukku, bajji, fish fry. |
| 9 | **Bengal gram flour (besan / kadalai maavu)** | Absent | Uses `ifct:B001 Bengal gram, dal`. Same material, ground. Affects bonda, bajji. |
| 10 | **Roasted gram (pottukadalai)** | Absent | Uses `ifct:B001`. Roasting changes moisture by a few percent. Affects coconut chutney. |
| 11 | **Urad flour** | Absent | Uses `ifct:B003`. Affects murukku. |
| 12 | **Cinnamon, bay leaf, fennel/saunf, star anise** | All absent from the Condiments group | Omitted from chicken curry and kurma. Sub-gram quantities. Noted so nobody later thinks it was an oversight. |
| 13 | **Sun-dried vathal (sundakkai, manathakkali)** | Absent | Vatha kuzhambu is the **small-onion (vengaya) version**, equally standard in Tamil Nadu. The literal sundakkai version cannot be expressed. |
| 14 | **Cooking soda / baking soda** | Absent | Omitted from bonda and bajji. Contributes sodium only (~27,000 mg Na per 100 g) at under 1 g per batch — so bajji sodium is slightly understated. |
| 15 | **Sago (javvarisi)** | Absent (`F015 Tapioca` is the root, not the pearl) | No dish needs it; javvarisi payasam was deliberately not attempted. |
| 16 | **Coconut milk** | Absent as its own item | Expressed as `ifct:H007 Coconut, kernel, fresh`, which is how it is made at home. **Overstates fibre**, because the squeezed residue is really discarded. Affects paruppu payasam, avial, kurma, chicken curry, kara kuzhambu. |
| 17 | **Appalam / papad** | No urad papad entry | Not attempted as a dish. Worth adding later if it is eaten regularly. |

Proxies 8–11 and 16 were reviewed and **accepted**, with their notes kept in the code.

## B. Points raised in the draft, and how they were decided

1. **The deep-fry oil assumption — KEPT AS DRAFTED.** 11–18% of finished weight is
   retained oil (medu vada 11%, masala vada 13%, bonda 11%, bajji 18%, murukku 15%,
   fish fry 10%). Published figures for Indian fried snacks span 8–25%, so this remains
   the single biggest error source in the document; moving it 5 points moves six dishes'
   fat and calories by up to 50%. **Each fried recipe now states its percentage in a
   comment** so the assumption is auditable and revisable in one place instead of being
   buried in a gram count.

2. **Coffee and tea infusion — FIXED.** The naive raw-mass model is gone. See decision 5
   and the note above the drinks section.

3. **Idli and dosa rice-to-dal ratio — 4:1.** Applied to idli, plain dosa, masala dosa
   and uttapam, with cooked weights, yields, serves and measures all recomputed.

4. **Rasam yield factors — KEPT AS DRAFTED** (tomato 3.30, pepper 5.75, lemon 4.45).
   These are dominated entirely by how much water goes in; a thicker pot raises every
   per-cup number proportionally.

5. **Kesari richness — HALVED.** Ghee 100 g → 50 g.

6. **Sakkarai pongal jaggery — REDUCED** 250 g → 150 g. **Ven pongal ghee — REDUCED**
   45 g → 30 g (6 g per serving, a weekday level). Sakkarai pongal's 60 g of ghee was
   left alone deliberately: it is a sweet, and halving the jaggery already took the
   richness down a long way. Flagged here rather than changed silently.

7. **Chicken cut — unchanged.** `ifct:N001 Chicken, poultry, leg, skinless`. The 600 g is
   boneless-equivalent EDIBLE weight; 600 g of curry cut with bone is closer to 420 g
   here. Noted in the code.

8. **Fish species — NOW A VARIANT SET.** Four species per fish dish rather than one
   hardcoded choice. See the box at the top of section 5.

9. **Avial souring agent — unchanged** (curd, the Tamil Nadu version). The Kerala version
   uses raw mango or tamarind and no curd, which changes the calcium contribution.

10. **Masala dosa yield of 1.00 — unchanged.** It falls out of the potato masala
    cancelling the batter's water gain. Arithmetically defensible; it just looks round.

11. **Serving sizes for the powders — REDEFINED.** `serves` is now the number of
    default-measure portions in a batch, so sambar powder "serves 140" means 140
    teaspoons, not 140 meals. A spice tin is not eaten in servings, and a fictional
    per-person number would have been worse than a large honest one.

## C. Structural rulings

1. **Yield factor = cooked weight ÷ sum of raw DRY ingredient grams.** The brief's
   "a dosa sits below 1.0" only holds on a batter basis; on a dry-grain basis a plain
   dosa is 1.70. The dry-grain reading is used throughout.

2. **Composite condiments stay inlined.** Sambar lists coriander seed and red chilli
   directly rather than referencing sambar powder as a dish. Sambar powder also exists
   as its own dish, so those spice rows appear twice on purpose. No dish-in-dish nesting
   was added — that would be a schema change.

3. **Slot tags for non-meal items.** Sambar powder, rasam powder and idli podi are tagged
   with the meals they appear in. If the app ever grows a `condiment` concept they should
   move to it.

4. **The five manual ingredients now exist** with full nutrient profiles and cited
   sources, in `backend/etl/load_manual_ingredients.py`. This was correctly identified as
   a Task 6 *prerequisite* rather than a side note: until salt existed, no dish
   containing it could produce a trustworthy number, and 57 of the 72 contain it.

## D. What is still worth a second look

* **The fried-snack oil percentages** (B1). Biggest lever in the document.
* **Rasam yield factors** (B4). Kept as drafted, but they are pot-dependent.
* **Curd composition.** `usda:curd` is a US retail yoghurt. Indian dahi is set from milk
  that is typically boiled and often buffalo, and soured further, so protein and fat sit
  a little low here and lactose a little high. No published Indian curd composition
  exists in IFCT; a real named USDA row still beats a hand-derivation from cow milk with
  the carbohydrate fudged.
* **Filter coffee decoction strength.** The USDA row is US drip strength, roughly a third
  of a South Indian decoction, so coffee-derived micronutrients are conservative. Energy,
  fat and protein are unaffected.
* **`usda:curd` iodine and `manual:sugar` iodine/biotin are NULL, not zero.** Unknown
  reads as unknown, deliberately.
* **Sodium overall.** Reviewed in fix round 1 and concluded broadly right: a modelled day
  totals ~9.9 g of salt, matching measured Indian intake of 8–11 g/day, and sambar at
  0.66% NaCl sits at or below normal palatability. Seven outliers were trimmed and a
  1.2%-of-finished-weight invariant now guards the whole set. What is still worth watching
  is that this is *modelled* salt — what the recipe says, not what the cook's hand does. If
  the hypertension rules fire more often than feels right, the per-dish salt grams are the
  thing to re-examine, not the salt composition, which is USDA-sourced and solid.
* **Oil and ghee energy is derived, not published.** IFCT publishes no usable energy figure
  for any fat, so all 14 carry an Atwater-derived ~900 kcal/100 g tagged `derived:atwater`.
  The number itself is not controversial — 100 g of fat is 900 kcal by definition — but it
  is the one place where a headline calorie figure here does not trace to a measured row.
