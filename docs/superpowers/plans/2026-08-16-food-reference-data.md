# Food & Reference Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the food and nutrient-reference database the whole app computes against — ingredients with verified nutrient values, editable South Indian dish recipes, reference dishes for eating out, and the ICMR-NIN requirement and upper-limit tables.

**Architecture:** Offline ETL scripts under `backend/etl/` transform four external sources into seed tables, each row carrying its provenance. Ingredients come from IFCT 2017 (unit-normalised), gap-filled from USDA for the two nutrients IFCT omits. South Indian dishes are authored as ingredient+gram recipes so they stay editable; INDB supplies non-editable reference dishes for restaurant and non-South-Indian food. A pure `foods/nutrition.py` module computes dish nutrients from recipes.

**Tech Stack:** Python 3.13, SQLAlchemy 2.0, Alembic, `httpx` for downloads, `openpyxl` for the INDB workbook, pytest. Existing FastAPI app from plan 1.

**Spec:** `docs/superpowers/specs/2026-08-15-south-indian-nutrient-tracker-design.md`

**Depends on:** Plan 1 (complete) — `app/models/base.py`, the model registry in `app/models/__init__.py`, and the `db` test fixture in `backend/tests/conftest.py` are all reused as-is.

## Global Constraints

- **Every row records its source.** `ingredients.source`, `dishes.source`, `rda_reference.source`, `upper_limits.source` are non-null. No number enters the database without provenance.
- **Canonical storage units are mg for minerals, µg for trace vitamins, g for proximates, kcal for energy.** Source units are converted on load, never stored raw. This is not cosmetic — see the verified findings below.
- **English only** for food and dish names.
- **Nothing in this plan is user-facing yet.** No new endpoints except the food search in Task 8; the UI arrives in plan 5.
- Reuse `TimestampedBase` from `app/models/base.py` for every new model, and register every new model in `app/models/__init__.py`.

---

## Verified source facts

These were confirmed by downloading and inspecting the actual data, not from documentation. They drive several design decisions, so re-verify if a source is re-fetched later.

**IFCT 2017** — mirror at `https://raw.githubusercontent.com/ifct2017/compositions/master/compositions/index.csv`, 542 foods × 421 columns, INFOODS tagname headers (`enerc`, `protcnt`, `ca`, `fe`, `vitb6c`, …) with a parallel `_e` error column for each.

- **Units are SI base units, not book units.** `ca = 0.121` for buffalo milk means **121 mg**; `enerc = 449` means **449 kJ**. Verified against three known foods (buffalo milk, brown rice, egg) — all matched published values only under the g/kJ reading. The printed IFCT book uses mg/µg/kcal, so anyone comparing the two will see a 1000× discrepancy and must not "fix" it.
- **No vitamin B12 and no iodine columns exist.** Both must come from USDA. This is load-bearing: B12 drives the vegetarian-observance compensation, iodine drives the thyroid rules and has an ICMR upper limit.
- Ships a **`tags`** column (e.g. `"vegetarian eggetarian fishetarian veg"`) which classifies each food for diet type and observance days — use it rather than hand-classifying 542 foods.
- Also ships `lang` with regional names including Tamil. The UI is English-only, but these are worth storing as **search aliases** so typing "keerai" finds amaranth.

**INDB** — `https://www.anuvaad.org.in/wp-content/uploads/2020/07/Anuvaad_INDB_2024.11.xlsx`, one sheet, 1,014 rows × 82 columns.

- Provides 39 nutrients **per 100 g and per serving**, plus a `servings_unit` household measure ("tea cup", "tall glass").
- **Contains no ingredient breakdown.** The earlier research claim that it carries ingredient amounts and cooked weights is wrong for this release. INDB dishes therefore cannot be made editable, and are imported as reference dishes only.
- South Indian coverage is thin: ~66 of 1,014 dishes match South Indian terms, with **pongal, poriyal, kootu and filter coffee entirely absent**. This is why Task 6 authors recipes by hand.
- Missing iodine and B12, like IFCT.

**USDA FoodData Central** — bulk CSV confirmed downloadable (`https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2025-04-24.zip`, 3.4 MB). CC0. Supplies B12, iodine, and western/packaged foods.

**ICMR-NIN 2020** — free extract at `https://www.nin.res.in/rdabook/brief_note.pdf`; upper limits in the scanned FSSAI-hosted committee report. Values are transcribed by hand and verified in a second pass (Task 5).

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app/models/nutrient.py` | `Nutrient` — the canonical nutrient list and units |
| `backend/app/models/food.py` | `Ingredient`, `IngredientNutrient`, `Dish`, `DishIngredient`, `PortionMeasure` |
| `backend/app/models/reference.py` | `RdaReference`, `UpperLimit` |
| `backend/app/foods/nutrition.py` | Pure functions: recipe → nutrient totals, per-100g scaling |
| `backend/app/foods/service.py` | Ingredient/dish queries and search |
| `backend/app/foods/router.py` | `GET /foods/search` |
| `backend/etl/common.py` | Download+cache helper, unit conversion, source tagging |
| `backend/etl/load_nutrients.py` | Seeds the canonical nutrient list |
| `backend/etl/load_ifct.py` | IFCT ingredients |
| `backend/etl/load_usda.py` | USDA gap-fill (B12, iodine, western foods) |
| `backend/etl/load_indb.py` | INDB reference dishes |
| `backend/etl/load_reference.py` | ICMR RDA/EAR/AI and upper limits |
| `backend/etl/recipes/south_indian.py` | The authored recipes as data |
| `backend/etl/run_all.py` | Idempotent orchestrator |

---

### Task 1: Canonical nutrient list

**Files:**
- Create: `backend/app/models/nutrient.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/etl/__init__.py`, `backend/etl/load_nutrients.py`
- Test: `backend/tests/test_nutrients_seed.py`

**Interfaces:**
- Produces: `Nutrient` (`code: str` unique, `display_name: str`, `unit: str`, `category: str`, `is_compensable: bool`, `compensation_days: int`, `is_excess_sensitive: bool`); `etl.load_nutrients.seed_nutrients(db) -> int`; the constant `NUTRIENTS: list[dict]`.

The nutrient row carries its own compensation classification, so `nutrition_core` in plan 3 reads policy from data instead of hardcoding it. Values come straight from the spec's compensability research.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_nutrients_seed.py`:

```python
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients


def test_seeding_creates_the_canonical_list(db):
    count = seed_nutrients(db)

    assert count >= 30
    assert db.query(Nutrient).filter_by(code="calcium").one().unit == "mg"
    assert db.query(Nutrient).filter_by(code="energy").one().unit == "kcal"


def test_protein_is_not_compensable(db):
    seed_nutrients(db)

    protein = db.query(Nutrient).filter_by(code="protein").one()

    assert protein.is_compensable is False
    assert protein.compensation_days == 0


def test_vitamin_k_carries_for_one_day_only(db):
    seed_nutrients(db)

    assert db.query(Nutrient).filter_by(code="vitamin_k").one().compensation_days == 1


def test_sodium_is_excess_sensitive_but_never_carried_up(db):
    seed_nutrients(db)

    sodium = db.query(Nutrient).filter_by(code="sodium").one()

    assert sodium.is_compensable is False
    assert sodium.is_excess_sensitive is True


def test_seeding_twice_is_idempotent(db):
    seed_nutrients(db)
    seed_nutrients(db)

    assert db.query(Nutrient).filter_by(code="iron").count() == 1
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_nutrients_seed.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.nutrient'`.

- [ ] **Step 3: Write the model**

Create `backend/app/models/nutrient.py`:

```python
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Nutrient(TimestampedBase):
    """One tracked nutrient, with the compensation policy that applies to it.

    Storing the policy here rather than in code means the compensation engine
    reads it as data, and the spec's research is represented in one place.
    """

    __tablename__ = "nutrients"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(8))  # kcal | g | mg | ug
    category: Mapped[str] = mapped_column(String(20))  # macro | mineral | vitamin

    # Can a shortfall be made up over following days?
    is_compensable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # How many days a shortfall may be spread over (0 when not compensable).
    compensation_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Does a harmful surplus warrant reducing following days' targets?
    is_excess_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 4: Write the seed data and loader**

Create `backend/etl/__init__.py` (empty) and `backend/etl/load_nutrients.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient

# (code, display_name, unit, category, compensable, days, excess_sensitive)
# Compensability follows the spec's research: protein has no storage pool,
# vitamin K's liver stores last days not weeks, fibre is capped for GI reasons,
# and a sodium shortfall is never something to make up.
NUTRIENTS: list[dict] = [
    dict(code="energy", display_name="Energy", unit="kcal", category="macro",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="protein", display_name="Protein", unit="g", category="macro",
         is_compensable=False, compensation_days=0, is_excess_sensitive=False),
    dict(code="fat", display_name="Total fat", unit="g", category="macro",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="saturated_fat", display_name="Saturated fat", unit="g", category="macro",
         is_compensable=False, compensation_days=0, is_excess_sensitive=True),
    dict(code="carbohydrate", display_name="Carbohydrate", unit="g", category="macro",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="free_sugar", display_name="Free sugar", unit="g", category="macro",
         is_compensable=False, compensation_days=0, is_excess_sensitive=True),
    dict(code="fibre", display_name="Dietary fibre", unit="g", category="macro",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="cholesterol", display_name="Cholesterol", unit="mg", category="macro",
         is_compensable=False, compensation_days=0, is_excess_sensitive=True),

    dict(code="calcium", display_name="Calcium", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="phosphorus", display_name="Phosphorus", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="magnesium", display_name="Magnesium", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="iron", display_name="Iron", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="zinc", display_name="Zinc", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="iodine", display_name="Iodine", unit="ug", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="selenium", display_name="Selenium", unit="ug", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="copper", display_name="Copper", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="manganese", display_name="Manganese", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="potassium", display_name="Potassium", unit="mg", category="mineral",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="sodium", display_name="Sodium", unit="mg", category="mineral",
         is_compensable=False, compensation_days=0, is_excess_sensitive=True),

    dict(code="vitamin_a", display_name="Vitamin A", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="vitamin_d", display_name="Vitamin D", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="vitamin_e", display_name="Vitamin E", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="vitamin_k", display_name="Vitamin K", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=1, is_excess_sensitive=False),
    dict(code="thiamine", display_name="Thiamine (B1)", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="riboflavin", display_name="Riboflavin (B2)", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="niacin", display_name="Niacin (B3)", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="pantothenic_acid", display_name="Pantothenic acid (B5)", unit="mg",
         category="vitamin", is_compensable=True, compensation_days=2,
         is_excess_sensitive=False),
    dict(code="vitamin_b6", display_name="Vitamin B6", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="biotin", display_name="Biotin (B7)", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="folate", display_name="Folate (B9)", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
    dict(code="vitamin_b12", display_name="Vitamin B12", unit="ug", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=False),
    dict(code="vitamin_c", display_name="Vitamin C", unit="mg", category="vitamin",
         is_compensable=True, compensation_days=2, is_excess_sensitive=True),
]


def seed_nutrients(db: Session) -> int:
    """Insert or update the canonical nutrient list. Safe to re-run."""
    existing = {n.code: n for n in db.scalars(select(Nutrient))}

    for spec in NUTRIENTS:
        nutrient = existing.get(spec["code"])
        if nutrient is None:
            db.add(Nutrient(**spec))
        else:
            for key, value in spec.items():
                setattr(nutrient, key, value)

    db.flush()
    return len(NUTRIENTS)
```

- [ ] **Step 5: Register the model**

In `backend/app/models/__init__.py`, add `from app.models.nutrient import Nutrient` alongside the existing imports and add `"Nutrient"` to `__all__`.

- [ ] **Step 6: Make `etl` importable from tests**

In `backend/pyproject.toml`, the `[tool.pytest.ini_options] pythonpath = ["."]` entry already puts the backend root on the path, so `import etl` works with no change. Confirm by running the test.

- [ ] **Step 7: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/test_nutrients_seed.py -v`
Expected: PASS — all five tests.

- [ ] **Step 8: Generate the migration**

```bash
cd backend
uv run alembic revision --autogenerate -m "create nutrients table"
uv run alembic upgrade head
uv run alembic check
```

Expected: `No new upgrade operations detected.`

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/nutrient.py backend/app/models/__init__.py backend/etl/ backend/tests/test_nutrients_seed.py backend/alembic/
git commit -m "feat: add canonical nutrient list with compensation policy"
```

---

### Task 2: Food and reference models

**Files:**
- Create: `backend/app/models/food.py`
- Create: `backend/app/models/reference.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_food_models.py`

**Interfaces:**
- Produces: `Ingredient` (`code`, `name`, `source`, `food_group`, `diet_tags`, `oxalate_class`, `search_aliases`); `IngredientNutrient` (`ingredient_id`, `nutrient_id`, `per_100g`); `Dish` (`code`, `name`, `source`, `is_editable`, `slot_tags`, `yield_factor`, `created_by_user_id`); `DishIngredient` (`dish_id`, `ingredient_id`, `grams`); `PortionMeasure` (`dish_id` / `ingredient_id`, `measure_name`, `grams`); `RdaReference`; `UpperLimit`.

Note the dish ownership rule from the spec: `created_by_user_id` nullable, **not** `household_id`. Null means a seed dish.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_food_models.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient


def _ingredient(db, code="ifct:A001", name="Amaranth seed"):
    ing = Ingredient(code=code, name=name, source="IFCT", food_group="Cereals")
    db.add(ing)
    db.flush()
    return ing


def test_ingredient_codes_are_unique(db):
    _ingredient(db)
    db.add(Ingredient(code="ifct:A001", name="Duplicate", source="IFCT"))

    with pytest.raises(IntegrityError):
        db.flush()


def test_nutrient_values_attach_to_an_ingredient(db):
    ing = _ingredient(db)
    calcium = Nutrient(
        code="calcium", display_name="Calcium", unit="mg", category="mineral"
    )
    db.add(calcium)
    db.flush()

    db.add(IngredientNutrient(ingredient_id=ing.id, nutrient_id=calcium.id, per_100g=181.0))
    db.flush()

    stored = db.query(IngredientNutrient).one()
    assert stored.per_100g == 181.0


def test_a_seed_dish_has_no_creator(db):
    dish = Dish(code="si:idli", name="Idli", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    assert dish.created_by_user_id is None
    assert dish.yield_factor == 1.0


def test_a_recipe_links_ingredients_with_gram_amounts(db):
    ing = _ingredient(db)
    dish = Dish(code="si:idli", name="Idli", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ing.id, grams=60.0))
    db.flush()

    assert db.query(DishIngredient).one().grams == 60.0
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_food_models.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.food'`.

- [ ] **Step 3: Write `backend/app/models/food.py`**

```python
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Ingredient(TimestampedBase):
    __tablename__ = "ingredients"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(16))  # IFCT | USDA | manual
    food_group: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # From IFCT's own `tags` column: "vegetarian eggetarian fishetarian veg".
    # Drives diet-type filtering and observance days.
    diet_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # "high" marks greens whose calcium is largely unavailable (palak, arai
    # keerai, colocasia); "low" marks murungai keerai, curry leaf, methi.
    # Spec research: spinach calcium absorption ~5% vs milk ~28-32%.
    oxalate_class: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Regional names from IFCT's `lang` column, so "keerai" finds amaranth.
    search_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngredientNutrient(TimestampedBase):
    __tablename__ = "ingredient_nutrients"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "nutrient_id", name="uq_ingredient_nutrient"),
    )

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    # Always in the nutrient's canonical unit, per 100 g of edible portion.
    per_100g: Mapped[float] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Dish(TimestampedBase):
    __tablename__ = "dishes"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(16))  # authored | INDB | user

    # Authored dishes have a recipe you can open and adjust. INDB reference
    # dishes carry fixed nutrients with no ingredient breakdown, so they are
    # not editable and count as estimated intake.
    is_editable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    slot_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)
    diet_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Cooked weight / raw ingredient weight. Rice absorbs water (>1), a dosa
    # loses it (<1). Used to express recipe totals per 100 g as served.
    yield_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Null for seed dishes; set for user-created ones. Deliberately NOT keyed
    # to a household — see the spec: dishes follow their author, so a solo
    # user's recipes survive joining or leaving a household.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )


class DishIngredient(TimestampedBase):
    __tablename__ = "dish_ingredients"

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    grams: Mapped[float] = mapped_column(Float)


class DishNutrient(TimestampedBase):
    """Fixed per-100g nutrients for dishes with no recipe (INDB imports)."""

    __tablename__ = "dish_nutrients"
    __table_args__ = (UniqueConstraint("dish_id", "nutrient_id", name="uq_dish_nutrient"),)

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    per_100g: Mapped[float] = mapped_column(Float)


class PortionMeasure(TimestampedBase):
    """A household measure — "1 idli", "1 tea cup" — and its gram weight."""

    __tablename__ = "portion_measures"

    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=True,
        index=True,
    )
    measure_name: Mapped[str] = mapped_column(String(60))
    grams: Mapped[float] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 4: Write `backend/app/models/reference.py`**

```python
import uuid

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class RdaReference(TimestampedBase):
    """An ICMR-NIN requirement value for one nutrient and demographic.

    `activity_level` is null for nutrients that do not scale with energy, and
    set for the four energy-scaled B vitamins (thiamine, riboflavin, niacin,
    B6) — the widely quoted ICMR figures are the *moderate* column, so a
    sedentary user given those is over-targeted by roughly 25%.
    """

    __tablename__ = "rda_reference"
    __table_args__ = (
        UniqueConstraint(
            "nutrient_id", "sex", "age_band", "activity_level", name="uq_rda_lookup"
        ),
    )

    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    sex: Mapped[str] = mapped_column(String(8))  # male | female
    age_band: Mapped[str] = mapped_column(String(16))  # 18-59 | 60+
    activity_level: Mapped[str | None] = mapped_column(String(12), nullable=True)

    ear: Mapped[float | None] = mapped_column(Float, nullable=True)
    rda: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(32))  # ICMR-NIN-2020 | IOM | EFSA


class UpperLimit(TimestampedBase):
    """A tolerable upper limit. Absent rows mean no ceiling was defined —
    ICMR deliberately set none for thiamine, riboflavin, biotin, B12 and
    potassium, so the app must not invent one."""

    __tablename__ = "upper_limits"
    __table_args__ = (UniqueConstraint("nutrient_id", "age_band", name="uq_ul_lookup"),)

    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    age_band: Mapped[str] = mapped_column(String(16), default="adult")
    value: Mapped[float] = mapped_column(Float)

    # True when the limit applies only to supplements, not food. Magnesium's
    # 350 mg UL is supplemental-only — warning on dietary magnesium is a bug.
    supplemental_only: Mapped[bool] = mapped_column(default=False, nullable=False)

    source: Mapped[str] = mapped_column(String(32))
```

- [ ] **Step 5: Register the models**

In `backend/app/models/__init__.py`, import `Dish`, `DishIngredient`, `DishNutrient`, `Ingredient`, `IngredientNutrient`, `PortionMeasure` from `app.models.food` and `RdaReference`, `UpperLimit` from `app.models.reference`, adding each to `__all__`.

- [ ] **Step 6: Run the test to confirm it passes**

Run: `cd backend && uv run pytest tests/test_food_models.py -v`
Expected: PASS — all four tests.

- [ ] **Step 7: Migrate and commit**

```bash
cd backend
uv run alembic revision --autogenerate -m "create food and reference tables"
uv run alembic upgrade head
uv run alembic check
git add backend/app/models/ backend/tests/test_food_models.py backend/alembic/
git commit -m "feat: add ingredient, dish, and nutrient-reference models"
```

---

### Task 3: IFCT ingredient loader

**Files:**
- Create: `backend/etl/common.py`
- Create: `backend/etl/load_ifct.py`
- Test: `backend/tests/test_load_ifct.py`
- Test fixture: `backend/tests/fixtures/ifct_sample.csv`

**Interfaces:**
- Produces: `etl.common.cached_download(url, filename) -> Path`; `etl.common.to_canonical(value, source_unit, target_unit) -> float`; `etl.load_ifct.IFCT_COLUMN_MAP: dict[str, tuple[str, str]]`; `etl.load_ifct.load_ifct(db, csv_path) -> int`.

**This is the task where the unit bug lives.** IFCT stores grams and kilojoules; we store mg/µg and kcal.

- [ ] **Step 1: Create the test fixture**

Create `backend/tests/fixtures/ifct_sample.csv` with the real header subset and three verified rows (values copied from the actual dataset, so the expected numbers below are the true published ones):

```csv
code,name,scie,lang,grup,regn,tags,enerc,protcnt,fatce,choavldf,fibtg,ca,fe,na,k,mg,zn,cu,se,p,mn,vita,vitd,vite,vitk1,thia,ribf,nia,pantac,vitb6c,biot,folsum,vitc
A001,"Amaranth seed, black",Amaranthus cruentus,"Tam. Keerai vidai","Cereals and Millets",1,"vegetarian eggetarian fishetarian veg",1490,14.59,5.56,58.0,7.02,0.181,0.00933,0.0242,0.508,0.248,0.0031,0.00075,0.0000185,0.455,0.0032,0.0000019,0,0.0012,0.0000009,0.0008,0.0002,0.0009,0.0011,0.00022,0.0000094,0.0000826,4.5
D005,"Milk, whole, Buffalo",Bubalus bubalis,"Tam. Erumai paal","Milk and Milk Products",1,"vegetarian eggetarian fishetarian veg",449,3.68,6.6,4.99,0,0.121,0.00016,0.0301,0.11,0.0134,0.00042,0.00002,0.0000019,0.0959,0.00001,0.0000335,0,0.00013,0.0000004,0.00004,0.00013,0.00009,0.00033,0.00004,0.0000021,0.0000053,1.5
E001,"Egg, poultry, whole, raw",Gallus domesticus,"Tam. Kozhi muttai","Egg and Egg Products",1,"eggetarian fishetarian",564,13.28,8.95,0.7,0,0.04944,0.00182,0.123,0.131,0.0116,0.00113,0.00005,0.0000312,0.181,0.00002,0.000156,0.0000018,0.00104,0.0000003,0.00004,0.00047,0.00007,0.00131,0.00012,0.0000201,0.0000471,0
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_load_ifct.py`. These assertions encode the verified real-world values — they are the guard against the 1000× unit error.

```python
from pathlib import Path

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_ifct import load_ifct
from etl.load_nutrients import seed_nutrients

FIXTURE = Path(__file__).parent / "fixtures" / "ifct_sample.csv"


def _value(db, ingredient_code, nutrient_code):
    return (
        db.query(IngredientNutrient)
        .join(Ingredient, Ingredient.id == IngredientNutrient.ingredient_id)
        .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
        .filter(Ingredient.code == ingredient_code, Nutrient.code == nutrient_code)
        .one()
        .per_100g
    )


def test_loads_every_row(db):
    seed_nutrients(db)

    count = load_ifct(db, FIXTURE)

    assert count == 3
    assert db.query(Ingredient).filter_by(source="IFCT").count() == 3


def test_energy_is_converted_from_kilojoules_to_kcal(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # 449 kJ / 4.184 = 107.3 kcal — buffalo milk is about 100 kcal/100 ml.
    assert _value(db, "ifct:D005", "energy") == pytest.approx(107.3, abs=0.5)


def test_calcium_is_converted_from_grams_to_milligrams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # The single most dangerous conversion: 0.121 g must become 121 mg,
    # not 0.121 mg. Getting this wrong understates calcium 1000-fold.
    assert _value(db, "ifct:D005", "calcium") == pytest.approx(121.0, abs=0.1)


def test_trace_nutrients_are_converted_from_grams_to_micrograms(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    # Egg vitamin A: 0.000156 g = 156 ug.
    assert _value(db, "ifct:E001", "vitamin_a") == pytest.approx(156.0, abs=1.0)


def test_proximates_stay_in_grams(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    assert _value(db, "ifct:E001", "protein") == pytest.approx(13.28, abs=0.01)


def test_diet_tags_and_aliases_are_kept(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    egg = db.query(Ingredient).filter_by(code="ifct:E001").one()
    amaranth = db.query(Ingredient).filter_by(code="ifct:A001").one()

    assert "eggetarian" in egg.diet_tags
    assert "vegetarian" not in egg.diet_tags
    assert "Keerai" in amaranth.search_aliases


def test_b12_and_iodine_are_absent_from_ifct(db):
    """IFCT publishes neither; they must come from USDA in Task 4."""
    seed_nutrients(db)
    load_ifct(db, FIXTURE)

    for code in ("vitamin_b12", "iodine"):
        assert (
            db.query(IngredientNutrient)
            .join(Nutrient)
            .filter(Nutrient.code == code)
            .count()
            == 0
        )


def test_loading_twice_does_not_duplicate(db):
    seed_nutrients(db)
    load_ifct(db, FIXTURE)
    load_ifct(db, FIXTURE)

    assert db.query(Ingredient).filter_by(code="ifct:A001").count() == 1
```

Add `import pytest` at the top of the file.

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_load_ifct.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'etl.load_ifct'`.

- [ ] **Step 4: Write `backend/etl/common.py`**

```python
from pathlib import Path

import httpx

CACHE_DIR = Path(__file__).parent / ".cache"

KCAL_PER_KJ = 1 / 4.184

# Multiplier to convert a source unit into a canonical unit.
_CONVERSIONS: dict[tuple[str, str], float] = {
    ("g", "g"): 1.0,
    ("g", "mg"): 1_000.0,
    ("g", "ug"): 1_000_000.0,
    ("mg", "mg"): 1.0,
    ("mg", "ug"): 1_000.0,
    ("mg", "g"): 0.001,
    ("ug", "ug"): 1.0,
    ("ug", "mg"): 0.001,
    ("kj", "kcal"): KCAL_PER_KJ,
    ("kcal", "kcal"): 1.0,
}


def to_canonical(value: float, source_unit: str, target_unit: str) -> float:
    """Convert a source value into the nutrient's canonical unit.

    IFCT's machine-readable mirror stores everything in SI base units — a
    calcium value of 0.121 means 121 mg — while the printed book uses mg and
    ug. Every load path goes through here so that difference is handled once.
    """
    try:
        factor = _CONVERSIONS[(source_unit.lower(), target_unit.lower())]
    except KeyError as exc:
        raise ValueError(f"No conversion from {source_unit} to {target_unit}") from exc
    return value * factor


def cached_download(url: str, filename: str) -> Path:
    """Download once into etl/.cache and reuse it on later runs."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / filename

    if not target.exists():
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with target.open("wb") as handle:
                for chunk in response.iter_bytes():
                    handle.write(chunk)

    return target
```

- [ ] **Step 5: Write `backend/etl/load_ifct.py`**

```python
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
```

- [ ] **Step 6: Add httpx as a runtime dependency**

```bash
cd backend && uv add httpx
```

(It is currently only a dev dependency via the test client.)

- [ ] **Step 7: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/test_load_ifct.py -v`
Expected: PASS — all eight tests, including the three unit-conversion assertions.

- [ ] **Step 8: Load the real dataset and sanity-check**

```bash
cd backend && uv run python -c "
from app.db import SessionLocal
from etl.common import cached_download
from etl.load_ifct import IFCT_URL, load_ifct
from etl.load_nutrients import seed_nutrients

db = SessionLocal()
seed_nutrients(db)
path = cached_download(IFCT_URL, 'ifct_compositions.csv')
print('ingredients loaded:', load_ifct(db, path))
db.commit()
"
```

Expected: `ingredients loaded: 542`.

- [ ] **Step 9: Commit**

```bash
git add backend/etl/ backend/tests/test_load_ifct.py backend/tests/fixtures/ backend/pyproject.toml backend/uv.lock
git commit -m "feat: load IFCT ingredients with verified unit normalisation"
```

---

### Task 4: USDA gap-fill for B12 and iodine

**Files:**
- Create: `backend/etl/load_usda.py`
- Test: `backend/tests/test_load_usda.py`

**Interfaces:**
- Produces: `etl.load_usda.load_usda_gapfill(db, food_csv, nutrient_csv, food_nutrient_csv) -> int`.

IFCT publishes neither B12 nor iodine, and both matter: B12 drives the vegetarian-observance compensation, iodine drives the thyroid rules and carries an ICMR upper limit. This task attaches those two nutrients to the IFCT ingredients that need them, matched by name, and imports a small set of western foods for restaurant logging.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_load_usda.py` using small CSV fixtures written inline via `tmp_path`, mirroring FoodData Central's `food.csv` / `nutrient.csv` / `food_nutrient.csv` layout:

```python
import pytest

from app.models.food import Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients
from etl.load_usda import load_usda_gapfill


@pytest.fixture
def usda_files(tmp_path):
    (tmp_path / "food.csv").write_text(
        "fdc_id,data_type,description\n"
        "1001,foundation_food,\"Milk, whole\"\n"
        "1002,foundation_food,\"Egg, whole, raw\"\n"
    )
    (tmp_path / "nutrient.csv").write_text(
        "id,name,unit_name\n"
        "1178,Vitamin B-12,UG\n"
        "1100,Iodine, I,UG\n"
    )
    (tmp_path / "food_nutrient.csv").write_text(
        "id,fdc_id,nutrient_id,amount\n"
        "1,1001,1178,0.45\n"
        "2,1002,1178,0.89\n"
    )
    return tmp_path


def test_attaches_b12_to_matching_ingredients(db, usda_files):
    seed_nutrients(db)
    milk = Ingredient(code="ifct:D005", name="Milk, whole, Buffalo", source="IFCT")
    db.add(milk)
    db.flush()

    load_usda_gapfill(
        db,
        usda_files / "food.csv",
        usda_files / "nutrient.csv",
        usda_files / "food_nutrient.csv",
    )

    value = (
        db.query(IngredientNutrient)
        .join(Nutrient)
        .filter(
            IngredientNutrient.ingredient_id == milk.id, Nutrient.code == "vitamin_b12"
        )
        .one()
    )
    assert value.per_100g == pytest.approx(0.45)
    assert value.source == "USDA"


def test_ifct_values_are_never_overwritten(db, usda_files):
    """USDA fills gaps; where IFCT has a value it wins, since it is the
    Indian composition authority for Indian foods."""
    seed_nutrients(db)
    milk = Ingredient(code="ifct:D005", name="Milk, whole, Buffalo", source="IFCT")
    db.add(milk)
    db.flush()
    b12 = db.query(Nutrient).filter_by(code="vitamin_b12").one()
    db.add(
        IngredientNutrient(
            ingredient_id=milk.id, nutrient_id=b12.id, per_100g=0.36, source="IFCT"
        )
    )
    db.flush()

    load_usda_gapfill(
        db,
        usda_files / "food.csv",
        usda_files / "nutrient.csv",
        usda_files / "food_nutrient.csv",
    )

    stored = db.query(IngredientNutrient).filter_by(ingredient_id=milk.id).one()
    assert stored.per_100g == pytest.approx(0.36)
    assert stored.source == "IFCT"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_load_usda.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'etl.load_usda'`.

- [ ] **Step 3: Write `backend/etl/load_usda.py`**

```python
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/test_load_usda.py -v`
Expected: PASS — both tests.

- [ ] **Step 5: Commit**

```bash
git add backend/etl/load_usda.py backend/tests/test_load_usda.py
git commit -m "feat: gap-fill B12 and iodine from USDA, preserving IFCT values"
```

---

### Task 5: ICMR-NIN reference values

**Files:**
- Create: `backend/etl/load_reference.py`
- Test: `backend/tests/test_load_reference.py`

**Interfaces:**
- Produces: `etl.load_reference.RDA_ROWS`, `etl.load_reference.UPPER_LIMIT_ROWS`, `etl.load_reference.seed_reference(db) -> tuple[int, int]`.

Values are transcribed by hand from the ICMR-NIN 2020 brief note and the ICMR upper-limit committee report. Each row records its source, and IOM/EFSA fallbacks are tagged as such so the UI can say which framework a number came from.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_load_reference.py`:

```python
import pytest

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit
from etl.load_nutrients import seed_nutrients
from etl.load_reference import seed_reference


def _rda(db, nutrient_code, sex, activity=None, age_band="18-59"):
    return (
        db.query(RdaReference)
        .join(Nutrient)
        .filter(
            Nutrient.code == nutrient_code,
            RdaReference.sex == sex,
            RdaReference.age_band == age_band,
            RdaReference.activity_level == activity,
        )
        .one()
    )


def test_calcium_matches_the_published_icmr_figure(db):
    seed_nutrients(db)
    seed_reference(db)

    calcium = _rda(db, "calcium", "male")

    assert calcium.rda == pytest.approx(1000)
    assert calcium.ear == pytest.approx(800)
    assert calcium.source == "ICMR-NIN-2020"


def test_womens_iron_is_higher_than_mens(db):
    """29 vs 19 mg — the female figure already averages menstrual loss across
    the cycle, which is why the cycle feature must not raise it further."""
    seed_nutrients(db)
    seed_reference(db)

    assert _rda(db, "iron", "female").rda == pytest.approx(29)
    assert _rda(db, "iron", "male").rda == pytest.approx(19)


def test_b_vitamins_are_indexed_by_activity(db):
    seed_nutrients(db)
    seed_reference(db)

    sedentary = _rda(db, "thiamine", "male", activity="sedentary")
    moderate = _rda(db, "thiamine", "male", activity="moderate")

    assert sedentary.rda == pytest.approx(1.4)
    assert moderate.rda == pytest.approx(1.8)
    assert sedentary.rda < moderate.rda


def test_elderly_calcium_and_vitamin_d_rise(db):
    seed_nutrients(db)
    seed_reference(db)

    assert _rda(db, "calcium", "male", age_band="60+").rda == pytest.approx(1200)


def test_magnesium_upper_limit_is_supplemental_only(db):
    seed_nutrients(db)
    seed_reference(db)

    magnesium = (
        db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == "magnesium").one()
    )

    assert magnesium.value == pytest.approx(350)
    assert magnesium.supplemental_only is True


def test_nutrients_icmr_left_open_have_no_upper_limit(db):
    """ICMR deliberately set none for these — the app must not invent one."""
    seed_nutrients(db)
    seed_reference(db)

    for code in ("thiamine", "riboflavin", "biotin", "vitamin_b12", "potassium"):
        assert (
            db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == code).count() == 0
        )


def test_iron_upper_limit_is_the_indian_value(db):
    seed_nutrients(db)
    seed_reference(db)

    iron = db.query(UpperLimit).join(Nutrient).filter(Nutrient.code == "iron").one()

    assert iron.value == pytest.approx(45)
    assert iron.source == "ICMR-2018-TUL"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_load_reference.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'etl.load_reference'`.

- [ ] **Step 3: Write `backend/etl/load_reference.py`**

Transcribe the tables. The structure below is complete for the values the spec cites; fill the remaining nutrients from the brief note in the same shape, and mark any value you cannot confirm with `source="UNVERIFIED"` rather than guessing.

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.nutrient import Nutrient
from app.models.reference import RdaReference, UpperLimit

ICMR = "ICMR-NIN-2020"
ICMR_TUL = "ICMR-2018-TUL"
IOM = "IOM"

# (nutrient, sex, age_band, activity, ear, rda, ai, source)
# Activity is set only for the four energy-scaled B vitamins. The commonly
# quoted ICMR B-vitamin numbers are the MODERATE column; applying them to a
# sedentary user over-targets by roughly 25%.
RDA_ROWS: list[tuple] = [
    ("protein", "male", "18-59", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "18-59", None, 36.3, 45.7, None, ICMR),
    ("protein", "male", "60+", None, 42.9, 54.0, None, ICMR),
    ("protein", "female", "60+", None, 36.3, 45.7, None, ICMR),

    ("calcium", "male", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "female", "18-59", None, 800, 1000, None, ICMR),
    ("calcium", "male", "60+", None, 800, 1200, None, ICMR),
    ("calcium", "female", "60+", None, 800, 1200, None, ICMR),

    ("iron", "male", "18-59", None, 11, 19, None, ICMR),
    ("iron", "female", "18-59", None, 15, 29, None, ICMR),
    ("iron", "male", "60+", None, 11, 19, None, ICMR),
    # ICMR publishes no postmenopausal category; the spec requires falling
    # back to the IOM value rather than applying the menstruating figure.
    ("iron", "female", "60+", None, 5, 8, None, IOM),

    ("magnesium", "male", "18-59", None, 370, 440, None, ICMR),
    ("magnesium", "female", "18-59", None, 310, 370, None, ICMR),
    ("zinc", "male", "18-59", None, 14, 17, None, ICMR),
    ("zinc", "female", "18-59", None, 11, 13.0, None, ICMR),
    ("iodine", "male", "18-59", None, 95, 150, None, ICMR),
    ("iodine", "female", "18-59", None, 95, 150, None, ICMR),
    ("sodium", "male", "18-59", None, None, None, 2000, ICMR),
    ("sodium", "female", "18-59", None, None, None, 2000, ICMR),
    ("potassium", "male", "18-59", None, None, None, 3510, ICMR),
    ("potassium", "female", "18-59", None, None, None, 3510, ICMR),
    ("selenium", "male", "18-59", None, None, None, 40, ICMR),
    ("selenium", "female", "18-59", None, None, None, 40, ICMR),

    ("vitamin_a", "male", "18-59", None, 460, 1000, None, ICMR),
    ("vitamin_a", "female", "18-59", None, 390, 840, None, ICMR),
    ("vitamin_d", "male", "18-59", None, None, 15, None, ICMR),   # 600 IU
    ("vitamin_d", "female", "18-59", None, None, 15, None, ICMR),
    ("vitamin_d", "male", "60+", None, None, 20, None, ICMR),     # 800 IU
    ("vitamin_d", "female", "60+", None, None, 20, None, ICMR),
    ("folate", "male", "18-59", None, 250, 300, None, ICMR),
    ("folate", "female", "18-59", None, 180, 220, None, ICMR),
    ("vitamin_b12", "male", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_b12", "female", "18-59", None, 2.0, 2.2, None, ICMR),
    ("vitamin_c", "male", "18-59", None, 65, 80, None, ICMR),
    ("vitamin_c", "female", "18-59", None, 55, 65, None, ICMR),

    # Energy-scaled B vitamins, by activity level.
    ("thiamine", "male", "18-59", "sedentary", None, 1.4, None, ICMR),
    ("thiamine", "male", "18-59", "moderate", None, 1.8, None, ICMR),
    ("thiamine", "male", "18-59", "heavy", None, 2.3, None, ICMR),
    ("thiamine", "female", "18-59", "sedentary", None, 1.4, None, ICMR),
    ("thiamine", "female", "18-59", "moderate", None, 1.7, None, ICMR),
    ("thiamine", "female", "18-59", "heavy", None, 2.2, None, ICMR),
    ("riboflavin", "male", "18-59", "sedentary", None, 2.0, None, ICMR),
    ("riboflavin", "male", "18-59", "moderate", None, 2.5, None, ICMR),
    ("riboflavin", "male", "18-59", "heavy", None, 3.2, None, ICMR),
    ("riboflavin", "female", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("riboflavin", "female", "18-59", "moderate", None, 2.4, None, ICMR),
    ("riboflavin", "female", "18-59", "heavy", None, 3.1, None, ICMR),
    ("niacin", "male", "18-59", "sedentary", None, 14, None, ICMR),
    ("niacin", "male", "18-59", "moderate", None, 18, None, ICMR),
    ("niacin", "male", "18-59", "heavy", None, 23, None, ICMR),
    ("niacin", "female", "18-59", "sedentary", None, 11, None, ICMR),
    ("niacin", "female", "18-59", "moderate", None, 14, None, ICMR),
    ("niacin", "female", "18-59", "heavy", None, 18, None, ICMR),
    ("vitamin_b6", "male", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("vitamin_b6", "male", "18-59", "moderate", None, 2.4, None, ICMR),
    ("vitamin_b6", "male", "18-59", "heavy", None, 3.1, None, ICMR),
    ("vitamin_b6", "female", "18-59", "sedentary", None, 1.9, None, ICMR),
    ("vitamin_b6", "female", "18-59", "moderate", None, 1.9, None, ICMR),
    ("vitamin_b6", "female", "18-59", "heavy", None, 2.4, None, ICMR),
]

# (nutrient, value, supplemental_only, source)
UPPER_LIMIT_ROWS: list[tuple] = [
    ("iron", 45, False, ICMR_TUL),
    ("zinc", 40, False, ICMR_TUL),
    ("calcium", 2500, False, ICMR_TUL),
    ("iodine", 900, False, ICMR_TUL),
    ("vitamin_a", 3000, False, ICMR_TUL),
    ("vitamin_d", 100, False, ICMR_TUL),
    ("vitamin_e", 1000, False, ICMR_TUL),
    ("niacin", 35, False, ICMR_TUL),
    ("vitamin_b6", 100, False, ICMR_TUL),
    ("folate", 1000, False, ICMR_TUL),
    ("vitamin_c", 2000, False, ICMR_TUL),
    # Supplemental only — excludes food and water. Warning on dietary
    # magnesium would be a bug.
    ("magnesium", 350, True, IOM),
    ("selenium", 400, False, IOM),
    ("copper", 10, False, IOM),
    ("manganese", 11, False, IOM),
    ("phosphorus", 4000, False, IOM),
    # Deliberately absent, because ICMR set none: thiamine, riboflavin,
    # biotin, vitamin_b12, potassium.
]


def seed_reference(db: Session) -> tuple[int, int]:
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}

    for code, sex, age_band, activity, ear, rda, ai, source in RDA_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(RdaReference).where(
                RdaReference.nutrient_id == nutrient.id,
                RdaReference.sex == sex,
                RdaReference.age_band == age_band,
                RdaReference.activity_level == activity,
            )
        )
        if row is None:
            row = RdaReference(
                nutrient_id=nutrient.id, sex=sex, age_band=age_band, activity_level=activity
            )
            db.add(row)
        row.ear, row.rda, row.ai, row.source = ear, rda, ai, source

    for code, value, supplemental_only, source in UPPER_LIMIT_ROWS:
        nutrient = nutrients.get(code)
        if nutrient is None:
            continue
        row = db.scalar(
            select(UpperLimit).where(
                UpperLimit.nutrient_id == nutrient.id, UpperLimit.age_band == "adult"
            )
        )
        if row is None:
            row = UpperLimit(nutrient_id=nutrient.id, age_band="adult")
            db.add(row)
        row.value, row.supplemental_only, row.source = value, supplemental_only, source

    db.flush()
    return len(RDA_ROWS), len(UPPER_LIMIT_ROWS)
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/test_load_reference.py -v`
Expected: PASS — all seven tests.

- [ ] **Step 5: Second verification pass**

Re-read the published tables and check every transcribed number a second time, per the spec's requirement for the scanned source. Record in the module docstring the date checked and which document each block came from.

- [ ] **Step 6: Commit**

```bash
git add backend/etl/load_reference.py backend/tests/test_load_reference.py
git commit -m "feat: seed ICMR-NIN requirement and upper-limit tables"
```

---

### Task 6: Authored South Indian recipes

**Files:**
- Create: `backend/etl/recipes/__init__.py`
- Create: `backend/etl/recipes/south_indian.py`
- Create: `backend/etl/load_recipes.py`
- Test: `backend/tests/test_load_recipes.py`

**Interfaces:**
- Produces: `etl.recipes.south_indian.RECIPES: list[Recipe]` where `Recipe` is a dataclass (`code`, `name`, `slot_tags`, `diet_tags`, `yield_factor`, `serves`, `measures`, `ingredients: list[tuple[str, float]]`); `etl.load_recipes.load_recipes(db, recipes) -> int`.

Recipes reference IFCT ingredients by code, so nutrients are computed rather than copied. Ingredient amounts are raw weights for one batch; `yield_factor` converts to cooked weight.

- [ ] **Step 1: Produce the review table before writing any recipe**

Draft the ~60–80 dishes and print them as a single markdown table — dish, serves, each ingredient with grams, and the basis for the proportions — to `docs/superpowers/specs/2026-08-16-seed-recipes.md`. **Stop and get this reviewed before proceeding**: these gram amounts determine every nutrient number the app produces, and the reviewer eats this food and will spot errors immediately.

Cover at minimum: idli, plain dosa, masala dosa, rava dosa, adai, uttapam, pongal (ven and sakkarai), upma, semiya upma, idiyappam, appam, puttu, plain rice, curd rice, lemon rice, tamarind rice, coconut rice, sambar, rasam (tomato, pepper, lemon), more kuzhambu, vatha kuzhambu, poriyal (beans, cabbage, carrot), kootu, avial, thoran, keerai masiyal, sundal, kara kuzhambu, fish curry, chicken curry, egg curry, omelette, coconut chutney, tomato chutney, coriander chutney, mint chutney, sambar powder, rasam powder, medu vada, masala vada, bonda, bajji, murukku, filter coffee (with and without sugar), tea, buttermilk/neer mor, payasam (semiya, paruppu), kesari.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_load_recipes.py`:

```python
import pytest

from app.models.food import Dish, DishIngredient, Ingredient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients
from etl.load_recipes import RecipeIngredientMissing, load_recipes
from etl.recipes.south_indian import RECIPES


@pytest.fixture
def rice_and_dal(db):
    seed_nutrients(db)
    for code, name in [("ifct:B001", "Rice, raw, milled"), ("ifct:C001", "Bengal gram dal")]:
        db.add(Ingredient(code=code, name=name, source="IFCT"))
    db.flush()


def test_loads_a_recipe_with_its_ingredients(db, rice_and_dal):
    recipes = [
        r for r in RECIPES if all(
            code in {"ifct:B001", "ifct:C001"} for code, _ in r.ingredients
        )
    ][:1]
    if not recipes:
        pytest.skip("no recipe limited to the fixture ingredients")

    load_recipes(db, recipes)

    dish = db.query(Dish).one()
    assert dish.is_editable is True
    assert dish.source == "authored"
    assert db.query(DishIngredient).filter_by(dish_id=dish.id).count() >= 1


def test_a_missing_ingredient_is_a_loud_failure(db, rice_and_dal):
    from etl.recipes.south_indian import Recipe

    bogus = Recipe(
        code="si:bogus",
        name="Bogus",
        slot_tags="lunch",
        diet_tags="vegetarian",
        yield_factor=1.0,
        serves=1,
        measures=[("serving", 100.0)],
        ingredients=[("ifct:DOES-NOT-EXIST", 50.0)],
    )

    with pytest.raises(RecipeIngredientMissing):
        load_recipes(db, [bogus])


def test_every_seed_recipe_references_real_ingredients(db):
    """Guards the whole seed set against typos in ingredient codes."""
    seed_nutrients(db)
    from etl.common import cached_download
    from etl.load_ifct import IFCT_URL, load_ifct

    load_ifct(db, cached_download(IFCT_URL, "ifct_compositions.csv"))
    known = {i.code for i in db.query(Ingredient).all()}

    missing = {
        code
        for recipe in RECIPES
        for code, _ in recipe.ingredients
        if code not in known
    }

    assert missing == set()


def test_the_seed_set_covers_the_staples(db):
    names = {r.name.lower() for r in RECIPES}
    for staple in ["idli", "sambar", "rasam", "curd rice", "filter coffee"]:
        assert any(staple in n for n in names), f"missing {staple}"
```

- [ ] **Step 3: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_load_recipes.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'etl.load_recipes'`.

- [ ] **Step 4: Write the recipe data structure**

Create `backend/etl/recipes/__init__.py` (empty) and start `backend/etl/recipes/south_indian.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    code: str
    name: str
    slot_tags: str          # space separated: breakfast lunch snack dinner
    diet_tags: str          # vegetarian | eggetarian | fishetarian | nonveg
    yield_factor: float     # cooked weight / raw weight
    serves: int
    measures: list[tuple[str, float]]   # ("1 idli", 45.0)
    ingredients: list[tuple[str, float]]  # (ifct code, raw grams per batch)


RECIPES: list[Recipe] = [
    Recipe(
        code="si:idli",
        name="Idli",
        slot_tags="breakfast snack",
        diet_tags="vegetarian",
        # Batter absorbs water and steams: cooked weight is well above raw.
        yield_factor=2.6,
        serves=10,
        measures=[("1 idli", 45.0), ("2 idli", 90.0), ("3 idli", 135.0)],
        ingredients=[
            ("ifct:B017", 200.0),   # Rice, parboiled milled
            ("ifct:C012", 100.0),   # Black gram dal, dehusked
            ("ifct:S001", 4.0),     # Salt
        ],
    ),
    # ... the remaining recipes from the reviewed table
]
```

Fill in the rest from the approved review table, using the exact IFCT codes verified in Task 3.

- [ ] **Step 5: Write the loader**

Create `backend/etl/load_recipes.py`:

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Dish, DishIngredient, Ingredient, PortionMeasure


class RecipeIngredientMissing(Exception):
    """A recipe references an ingredient code that is not in the database."""


def load_recipes(db: Session, recipes) -> int:
    ingredients = {i.code: i for i in db.scalars(select(Ingredient))}
    loaded = 0

    for recipe in recipes:
        missing = [code for code, _ in recipe.ingredients if code not in ingredients]
        if missing:
            raise RecipeIngredientMissing(f"{recipe.code} references unknown {missing}")

        dish = db.scalar(select(Dish).where(Dish.code == recipe.code))
        if dish is None:
            dish = Dish(code=recipe.code, source="authored", is_editable=True)
            db.add(dish)
        dish.name = recipe.name
        dish.slot_tags = recipe.slot_tags
        dish.diet_tags = recipe.diet_tags
        dish.yield_factor = recipe.yield_factor
        db.flush()

        db.query(DishIngredient).filter_by(dish_id=dish.id).delete()
        for code, grams in recipe.ingredients:
            db.add(
                DishIngredient(
                    dish_id=dish.id, ingredient_id=ingredients[code].id, grams=grams
                )
            )

        db.query(PortionMeasure).filter_by(dish_id=dish.id).delete()
        for index, (measure_name, grams) in enumerate(recipe.measures):
            db.add(
                PortionMeasure(
                    dish_id=dish.id,
                    measure_name=measure_name,
                    grams=grams,
                    is_default=(index == 0),
                )
            )

        loaded += 1

    db.flush()
    return loaded
```

- [ ] **Step 6: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/test_load_recipes.py -v`
Expected: PASS — all four tests, including the one proving every recipe's ingredient codes exist in the real IFCT data.

- [ ] **Step 7: Commit**

```bash
git add backend/etl/recipes/ backend/etl/load_recipes.py backend/tests/test_load_recipes.py docs/superpowers/specs/2026-08-16-seed-recipes.md
git commit -m "feat: add authored South Indian recipes seeded against IFCT ingredients"
```

---

### Task 7: Dish nutrient computation and INDB reference dishes

**Files:**
- Create: `backend/app/foods/__init__.py`, `backend/app/foods/nutrition.py`
- Create: `backend/etl/load_indb.py`
- Test: `backend/tests/test_dish_nutrition.py`
- Test: `backend/tests/test_load_indb.py`

**Interfaces:**
- Produces: `app.foods.nutrition.compute_dish_nutrients(db, dish) -> dict[str, float]` (per 100 g as served) and `nutrients_for_portion(db, dish, grams) -> dict[str, float]`; `etl.load_indb.load_indb(db, xlsx_path) -> int`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_dish_nutrition.py`:

```python
import pytest

from app.foods.nutrition import compute_dish_nutrients, nutrients_for_portion
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from app.models.nutrient import Nutrient
from etl.load_nutrients import seed_nutrients


@pytest.fixture
def simple_dish(db):
    seed_nutrients(db)
    protein = db.query(Nutrient).filter_by(code="protein").one()

    rice = Ingredient(code="t:rice", name="Rice", source="IFCT")
    dal = Ingredient(code="t:dal", name="Dal", source="IFCT")
    db.add_all([rice, dal])
    db.flush()
    # 7 g protein per 100 g rice, 23 g per 100 g dal.
    db.add(IngredientNutrient(ingredient_id=rice.id, nutrient_id=protein.id, per_100g=7.0))
    db.add(IngredientNutrient(ingredient_id=dal.id, nutrient_id=protein.id, per_100g=23.0))

    dish = Dish(code="t:dish", name="Test dish", source="authored", is_editable=True,
                yield_factor=2.0)
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=rice.id, grams=100.0))
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=dal.id, grams=100.0))
    db.flush()
    return dish


def test_totals_are_expressed_per_100g_as_served(db, simple_dish):
    # 7 g + 23 g = 30 g protein in 200 g raw, which yields 400 g cooked,
    # so 7.5 g per 100 g as served.
    values = compute_dish_nutrients(db, simple_dish)

    assert values["protein"] == pytest.approx(7.5)


def test_a_portion_scales_from_the_per_100g_figure(db, simple_dish):
    values = nutrients_for_portion(db, simple_dish, grams=200.0)

    assert values["protein"] == pytest.approx(15.0)


def test_an_empty_recipe_yields_nothing_rather_than_failing(db):
    seed_nutrients(db)
    dish = Dish(code="t:empty", name="Empty", source="authored", is_editable=True)
    db.add(dish)
    db.flush()

    assert compute_dish_nutrients(db, dish) == {}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_dish_nutrition.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.foods'`.

- [ ] **Step 3: Write `backend/app/foods/nutrition.py`**

```python
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Dish, DishIngredient, DishNutrient, IngredientNutrient
from app.models.nutrient import Nutrient


def compute_dish_nutrients(db: Session, dish: Dish) -> dict[str, float]:
    """Nutrients per 100 g of the dish as served.

    Authored dishes are summed from their recipe and divided by the cooked
    weight, so `yield_factor` matters: rice absorbs water and dilutes per-gram
    values, a dosa loses water and concentrates them. Imported dishes carry
    fixed per-100g values instead, since they have no recipe.
    """
    rows = list(
        db.execute(
            select(DishIngredient, IngredientNutrient, Nutrient)
            .join(
                IngredientNutrient,
                IngredientNutrient.ingredient_id == DishIngredient.ingredient_id,
            )
            .join(Nutrient, Nutrient.id == IngredientNutrient.nutrient_id)
            .where(DishIngredient.dish_id == dish.id)
        )
    )

    if not rows:
        fixed = list(
            db.execute(
                select(DishNutrient, Nutrient)
                .join(Nutrient, Nutrient.id == DishNutrient.nutrient_id)
                .where(DishNutrient.dish_id == dish.id)
            )
        )
        return {nutrient.code: value.per_100g for value, nutrient in fixed}

    totals: dict[str, float] = {}
    raw_grams = 0.0
    seen_ingredients: set = set()

    for dish_ingredient, ingredient_nutrient, nutrient in rows:
        if dish_ingredient.id not in seen_ingredients:
            raw_grams += dish_ingredient.grams
            seen_ingredients.add(dish_ingredient.id)
        contribution = ingredient_nutrient.per_100g * dish_ingredient.grams / 100.0
        totals[nutrient.code] = totals.get(nutrient.code, 0.0) + contribution

    cooked_grams = raw_grams * (dish.yield_factor or 1.0)
    if cooked_grams <= 0:
        return {}

    return {code: total * 100.0 / cooked_grams for code, total in totals.items()}


def nutrients_for_portion(db: Session, dish: Dish, grams: float) -> dict[str, float]:
    per_100g = compute_dish_nutrients(db, dish)
    return {code: value * grams / 100.0 for code, value in per_100g.items()}
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `cd backend && uv run pytest tests/test_dish_nutrition.py -v`
Expected: PASS — all three tests.

- [ ] **Step 5: Write the INDB loader**

Create `backend/etl/load_indb.py`. Its 82 columns map per-100g values directly; the `unit_serving_*` block gives the household measure.

```python
from pathlib import Path

import openpyxl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.food import Dish, DishNutrient, PortionMeasure
from app.models.nutrient import Nutrient

INDB_URL = "https://www.anuvaad.org.in/wp-content/uploads/2020/07/Anuvaad_INDB_2024.11.xlsx"

# INDB column -> (nutrient code, source unit). INDB has no iodine or B12.
INDB_COLUMN_MAP: dict[str, tuple[str, str]] = {
    "energy_kcal": ("energy", "kcal"),
    "protein_g": ("protein", "g"),
    "fat_g": ("fat", "g"),
    "carb_g": ("carbohydrate", "g"),
    "freesugar_g": ("free_sugar", "g"),
    "fibre_g": ("fibre", "g"),
    "sfa_mg": ("saturated_fat", "mg"),
    "cholesterol_mg": ("cholesterol", "mg"),
    "calcium_mg": ("calcium", "mg"),
    "phosphorus_mg": ("phosphorus", "mg"),
    "magnesium_mg": ("magnesium", "mg"),
    "sodium_mg": ("sodium", "mg"),
    "potassium_mg": ("potassium", "mg"),
    "iron_mg": ("iron", "mg"),
    "copper_mg": ("copper", "mg"),
    "selenium_ug": ("selenium", "ug"),
    "manganese_mg": ("manganese", "mg"),
    "zinc_mg": ("zinc", "mg"),
    "vita_ug": ("vitamin_a", "ug"),
    "vite_mg": ("vitamin_e", "mg"),
    "vitk1_ug": ("vitamin_k", "ug"),
    "folate_ug": ("folate", "ug"),
    "vitb1_mg": ("thiamine", "mg"),
    "vitb2_mg": ("riboflavin", "mg"),
    "vitb3_mg": ("niacin", "mg"),
    "vitb5_mg": ("pantothenic_acid", "mg"),
    "vitb6_mg": ("vitamin_b6", "mg"),
    "vitb7_ug": ("biotin", "ug"),
    "vitc_mg": ("vitamin_c", "mg"),
}


def load_indb(db: Session, xlsx_path: Path) -> int:
    from etl.common import to_canonical

    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    workbook = openpyxl.load_workbook(xlsx_path, read_only=True)
    sheet = workbook[workbook.sheetnames[0]]

    rows = sheet.iter_rows(values_only=True)
    header = {name: index for index, name in enumerate(next(rows))}
    loaded = 0

    for row in rows:
        code = f"indb:{row[header['food_code']]}"
        dish = db.scalar(select(Dish).where(Dish.code == code))
        if dish is None:
            # Not editable: INDB ships no ingredient breakdown, so these are
            # reference entries and their intake counts as estimated.
            dish = Dish(code=code, source="INDB", is_editable=False)
            db.add(dish)
        dish.name = row[header["food_name"]]
        db.flush()

        for column, (nutrient_code, unit) in INDB_COLUMN_MAP.items():
            nutrient = nutrients.get(nutrient_code)
            value = row[header[column]] if column in header else None
            if nutrient is None or value in (None, ""):
                continue

            existing = db.scalar(
                select(DishNutrient).where(
                    DishNutrient.dish_id == dish.id,
                    DishNutrient.nutrient_id == nutrient.id,
                )
            )
            converted = to_canonical(float(value), unit, nutrient.unit)
            if existing is None:
                db.add(
                    DishNutrient(
                        dish_id=dish.id, nutrient_id=nutrient.id, per_100g=converted
                    )
                )
            else:
                existing.per_100g = converted

        serving_unit = row[header["servings_unit"]]
        serving_kcal = row[header["unit_serving_energy_kcal"]]
        per_100g_kcal = row[header["energy_kcal"]]
        if serving_unit and serving_kcal and per_100g_kcal:
            grams = float(serving_kcal) * 100.0 / float(per_100g_kcal)
            if not db.scalar(
                select(PortionMeasure).where(
                    PortionMeasure.dish_id == dish.id,
                    PortionMeasure.measure_name == serving_unit,
                )
            ):
                db.add(
                    PortionMeasure(
                        dish_id=dish.id,
                        measure_name=str(serving_unit),
                        grams=grams,
                        is_default=True,
                    )
                )

        loaded += 1

    db.flush()
    return loaded
```

- [ ] **Step 6: Write the INDB test**

Create `backend/tests/test_load_indb.py` building a tiny workbook with `openpyxl` in `tmp_path`, asserting: a dish is created with `source="INDB"` and `is_editable=False`; its calcium lands in mg; a portion measure is derived from the serving energy; and re-running does not duplicate.

- [ ] **Step 7: Add openpyxl and run**

```bash
cd backend && uv add openpyxl
uv run pytest tests/test_load_indb.py tests/test_dish_nutrition.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/foods/ backend/etl/load_indb.py backend/tests/test_dish_nutrition.py backend/tests/test_load_indb.py backend/pyproject.toml backend/uv.lock
git commit -m "feat: compute dish nutrients from recipes and import INDB reference dishes"
```

---

### Task 8: Orchestrator and food search endpoint

**Files:**
- Create: `backend/etl/run_all.py`
- Create: `backend/app/foods/service.py`, `backend/app/foods/router.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_foods_api.py`

**Interfaces:**
- Produces: `etl.run_all.main() -> None`; `app.foods.service.search_foods(db, query, limit) -> list[dict]`; `GET /foods/search?q=...`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_foods_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.main import app
from app.models.food import Dish, Ingredient
from etl.load_nutrients import seed_nutrients


@pytest.fixture
def api(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_in(api, monkeypatch):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "s1", "email": "a@example.com", "email_verified": True, "name": "A"
        },
    )
    api.post("/auth/google", json={"credential": "t"})


def test_search_finds_dishes_and_ingredients(db, api, monkeypatch):
    seed_nutrients(db)
    db.add(Dish(code="si:idli", name="Idli", source="authored", is_editable=True))
    db.add(Ingredient(code="ifct:A001", name="Amaranth seed", source="IFCT",
                      search_aliases="Tam. Keerai vidai"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=idli").json()

    assert any(r["name"] == "Idli" and r["kind"] == "dish" for r in results)


def test_search_matches_regional_aliases(db, api, monkeypatch):
    seed_nutrients(db)
    db.add(Ingredient(code="ifct:A001", name="Amaranth seed", source="IFCT",
                      search_aliases="Tam. Keerai vidai"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=keerai").json()

    assert any(r["name"] == "Amaranth seed" for r in results)


def test_search_requires_sign_in(api):
    assert api.get("/foods/search?q=idli").status_code == 401
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd backend && uv run pytest tests/test_foods_api.py -q`
Expected: FAIL — 404 on the route.

- [ ] **Step 3: Write the service and router**

`backend/app/foods/service.py`:

```python
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.food import Dish, Ingredient


def search_foods(db: Session, query: str, limit: int = 20) -> list[dict]:
    """Search dishes and ingredients by name or regional alias."""
    pattern = f"%{query.strip()}%"

    dishes = db.scalars(
        select(Dish).where(Dish.name.ilike(pattern)).limit(limit)
    ).all()
    ingredients = db.scalars(
        select(Ingredient)
        .where(
            or_(
                Ingredient.name.ilike(pattern),
                Ingredient.search_aliases.ilike(pattern),
            )
        )
        .limit(limit)
    ).all()

    results = [
        {
            "id": str(d.id),
            "kind": "dish",
            "name": d.name,
            "source": d.source,
            "is_editable": d.is_editable,
        }
        for d in dishes
    ] + [
        {
            "id": str(i.id),
            "kind": "ingredient",
            "name": i.name,
            "source": i.source,
            "is_editable": False,
        }
        for i in ingredients
    ]
    return results[:limit]
```

`backend/app/foods/router.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.foods import service
from app.models.user import User

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search")
def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return service.search_foods(db, q, limit)
```

Register it in `backend/app/main.py` beside the existing routers.

- [ ] **Step 4: Write the orchestrator**

`backend/etl/run_all.py`:

```python
"""Seed the food and reference database. Idempotent: safe to re-run."""

from app.db import SessionLocal
from etl.common import cached_download
from etl.load_ifct import IFCT_URL, load_ifct
from etl.load_indb import INDB_URL, load_indb
from etl.load_nutrients import seed_nutrients
from etl.load_recipes import load_recipes
from etl.load_reference import seed_reference
from etl.recipes.south_indian import RECIPES


def main() -> None:
    db = SessionLocal()
    try:
        print("nutrients:", seed_nutrients(db))
        print("reference rows:", seed_reference(db))

        ifct = cached_download(IFCT_URL, "ifct_compositions.csv")
        print("ingredients:", load_ifct(db, ifct))

        print("recipes:", load_recipes(db, RECIPES))

        indb = cached_download(INDB_URL, "indb.xlsx")
        print("reference dishes:", load_indb(db, indb))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run everything**

```bash
cd backend
uv run pytest -v
uv run ruff check .
uv run python -m etl.run_all
```

Expected: all tests pass; the ETL prints roughly `ingredients: 542`, `recipes: 60-80`, `reference dishes: 1014`.

- [ ] **Step 6: Verify the seeded data by hand**

```bash
docker compose exec -T db psql -U healthmonitor -d healthmonitor -c "
  select source, count(*) from ingredients group by source;
  select source, count(*) from dishes group by source;
  select n.code, i.per_100g from ingredient_nutrients i
    join nutrients n on n.id = i.nutrient_id
    join ingredients g on g.id = i.ingredient_id
   where g.name like 'Milk, whole, Buffalo%' and n.code in ('calcium','energy');
"
```

Expected: calcium ≈ 121 (mg) and energy ≈ 107 (kcal) for buffalo milk — the two values that prove unit normalisation is right end to end.

- [ ] **Step 7: Commit**

```bash
git add backend/app/foods/ backend/etl/run_all.py backend/app/main.py backend/tests/test_foods_api.py
git commit -m "feat: add ETL orchestrator and authenticated food search"
```

---

## Self-Review

**Spec coverage.** Ingredients with source tagging (Task 3), the mandatory USDA gap-fill for the two nutrients IFCT omits (Task 4), ICMR EAR/RDA/AI with activity-indexed B vitamins and upper limits including the supplemental-only magnesium flag (Task 5), editable South Indian recipes (Task 6), restaurant/non-South-Indian dishes as estimated entries (Task 7), oxalate class and regional search aliases (Task 2 columns, both written by the IFCT loader in Task 3 — aliases from IFCT's `lang` column for every food, oxalate class from an explicit map covering the greens the spec names), dish ownership by creator rather than household (Task 2). The compensation policy per nutrient is seeded in Task 1 so plan 3 reads it as data.

**Deliberate deferrals.** Nutrient *retention* factors — the losses of vitamin C, thiamine and folate during cooking — are not modelled; only the water-based `yield_factor` is. This overstates heat-sensitive vitamins in cooked dishes and should be added before the weekly report claims precision about them. The oxalate class is set for the eleven greens the spec names (`etl.load_ifct.OXALATE_CLASS`: amaranth, spinach and colocasia leaves `high`; drumstick, fenugreek, coriander and curry leaves `low`) and is deliberately NULL elsewhere — not exhaustively classified across all 542 ingredients, and NULL must be read as "not classified", never as "low". The whole-vs-hulled sesame split the spec also asks for is **not** delivered: IFCT publishes gingelly seeds by colour (black `ifct:H009`, brown `H010`, white `H011`) and has no hulled/dehulled entry at all, so the distinction the spec cares about — the calcium lives in the hull — cannot be made from this source and needs a non-IFCT composition before the calcium maths can honour it. USDA import is limited to B12, iodine and matched foods rather than the full branded database.

**Placeholder check.** Task 6 Step 4 deliberately contains one `...` continuation, because the recipe list is produced by the Step 1 review and cannot be invented before the reviewer approves the gram amounts. Every other step contains complete code.

**Type consistency.** `to_canonical(value, source_unit, target_unit)` is used identically in `load_ifct`, `load_usda` and `load_indb`. `Nutrient.unit` values (`kcal`/`g`/`mg`/`ug`) are exactly the target units in the `_CONVERSIONS` table. `compute_dish_nutrients` returns `dict[str, float]` keyed by nutrient code, which `nutrients_for_portion` scales and plan 5's diary will consume. `Dish.is_editable` distinguishes authored recipes from INDB imports consistently across Tasks 2, 6 and 7.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-16-food-reference-data.md`. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, reviewed between tasks.

**2. Inline Execution** — tasks executed in this session, batched with checkpoints.

Note that **Task 6 Step 1 is a hard stop for review**: the seed recipe gram amounts must be approved before they are encoded, because every nutrient number the app produces depends on them.
