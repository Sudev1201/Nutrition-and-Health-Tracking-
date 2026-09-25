"""AI descriptions for the dishes in a plan: what is sent, what is kept, where it lives.

Nothing the planner decides passes through here. The model is shown each dish's
name and its ingredients' names, and nothing else: no portion, gram, nutrient,
rationale (which can name a medication and a percentage) or anything from the
profile. What comes back is kept only when `clean` finds no amount in it (no
digit, no "%", and no number, multiplier, unit or household measure in words)
and none of the nutrient words it lists. That is a word list, not a reader: it
does not catch every nutrition or health claim, and "rich in iron" passes. The
text reaches the plan as two new fields beside the planner's own, never in
place of them.

The text is cached per user and dish, keyed by a hash of exactly what was sent.
Nothing is keyed to a plan item, so a swap, a lock, a regenerate or a re-plan
needs no invalidation: a dish shows its own text, or none.
"""

import hashlib
import re
import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.llm import service as llm
from app.llm.providers import PROMPT_VERSION, DishBrief, DishText, Provider
from app.models.food import Dish, DishIngredient, Ingredient
from app.models.llm import DishPolish
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User

# Well past the prompt's 25-word sentence and 30-word tip, so only a runaway
# answer is refused. Refused, not cut: half a sentence is worse than none.
MAX_TEXT = 280
# One structured-output call per this many dishes. A week holds 15 to 25
# distinct dishes, so one call is the usual case; the cap keeps a very varied
# week's answer well inside the call's max_tokens.
MAX_DISHES_PER_CALL = 40

# Words that state an amount, change a portion or name a nutrient. Matched as
# whole words, case-insensitively, where a word is a run of ASCII letters.
BANNED_WORDS: frozenset[str] = frozenset(
    {
        # numbers in words
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "thousand",
        "half",
        "quarter",
        "dozen",
        "percent",
        # multipliers: "double the dal" changes the planner's portion without a number
        "twice",
        "double",
        "triple",
        "halve",
        "halved",
        # units ("gram" is left out: Bengal, black, green and red gram are the pulses in
        # most of the seeded recipes, and a number in front of it is refused anyway)
        "grams",
        "kg",
        "mg",
        "mcg",
        "ml",
        "litre",
        "litres",
        "liter",
        "liters",
        "kcal",
        "calorie",
        "calories",
        "cup",
        "cups",
        "tablespoon",
        "tablespoons",
        "teaspoon",
        "teaspoons",
        "tbsp",
        "tsp",
        "serving",
        "servings",
        "portion",
        "portions",
        # household measures: the planner writes portions in these ("1 katori")
        "katori",
        "katoris",
        "tumbler",
        "tumblers",
        "ladle",
        "ladles",
        "ladleful",
        # nutrient words ("iron" is left out: "a cast-iron pan" is a cooking tip)
        "protein",
        "proteins",
        "calcium",
        "vitamin",
        "vitamins",
        "fibre",
        "fiber",
        "carbohydrate",
        "carbohydrates",
        "carbs",
        "sodium",
        "potassium",
        "cholesterol",
        "nutrient",
        "nutrients",
        "nutritious",
    }
)

_WORD = re.compile(r"[A-Za-z]+")


class NoKey(LookupError):
    """The user has no usable key: none saved, or one marked rejected or unreadable."""


def clean(text: str | None) -> str | None:
    """The text, stripped, when it is fit to show beside a plan; None when it is not.

    Fit means non-empty, at most MAX_TEXT characters, with no digit or other
    numeric character ("½" included), no "%", and no word from BANNED_WORDS:
    numbers, multipliers, units and household measures in words, and a list of
    nutrient words. Words are runs of letters, so "cast-iron" is two words and
    passes, "someone" is one word and passes, and "one-pot" contains the word
    "one" and is refused. The guard errs toward losing a tip rather than showing
    an amount beside the planner's portion. It matches words, not meaning, so it
    does not catch every nutrition or health claim.
    """
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_TEXT:
        return None
    if "%" in stripped or any(char.isnumeric() for char in stripped):
        return None
    if any(word.lower() in BANNED_WORDS for word in _WORD.findall(stripped)):
        return None
    return stripped


def brief_hash(name: str, ingredients: Sequence[str]) -> str:
    """A fingerprint of what the model was shown for one dish, and under which prompt.

    A cached text whose fingerprint no longer matches -- the dish or one of its
    ingredients renamed by a re-seed, or a new PROMPT_VERSION -- is ignored, and
    the next polish replaces it.
    """
    payload = "\n".join([f"v{PROMPT_VERSION}", name, *ingredients])
    return hashlib.sha256(payload.encode()).hexdigest()


def dish_briefs(
    db: Session, dish_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, tuple[str, tuple[str, ...]]]:
    """Each dish's name and its ingredients' names, sorted and without repeats.

    This is everything the model is ever shown about a dish. One query; a dish
    with no ingredient rows (a fixed-nutrient reference dish) gets ().
    """
    ids = set(dish_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Dish.id, Dish.name, Ingredient.name)
        .outerjoin(DishIngredient, DishIngredient.dish_id == Dish.id)
        .outerjoin(Ingredient, Ingredient.id == DishIngredient.ingredient_id)
        .where(Dish.id.in_(ids))
    ).all()

    names: dict[uuid.UUID, str] = {}
    ingredients: dict[uuid.UUID, set[str]] = {}
    for dish_id, dish_name, ingredient_name in rows:
        names[dish_id] = dish_name
        found = ingredients.setdefault(dish_id, set())
        if ingredient_name is not None:
            found.add(ingredient_name)
    return {dish_id: (name, tuple(sorted(ingredients[dish_id]))) for dish_id, name in names.items()}


def current_polish(
    db: Session, user: User, dish_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, DishText]:
    """This user's cached text for these dishes, where it still matches the dish.

    Read by dish, never by plan item, and only ever for the signed-in user's own
    plan: nothing on the household path calls this.
    """
    ids = set(dish_ids)
    if not ids:
        return {}
    # Columns rather than DishPolish objects. `_keep` writes with a Core upsert,
    # which never refreshes an ORM object, and a column read cannot go stale.
    rows = db.execute(
        select(
            DishPolish.dish_id,
            DishPolish.brief_hash,
            DishPolish.description,
            DishPolish.cooking_note,
        ).where(DishPolish.user_id == user.id, DishPolish.dish_id.in_(ids))
    ).all()
    if not rows:
        return {}

    briefs = dish_briefs(db, (row.dish_id for row in rows))
    return {
        row.dish_id: DishText(row.description, row.cooking_note)
        for row in rows
        if row.dish_id in briefs and row.brief_hash == brief_hash(*briefs[row.dish_id])
    }


def polish_week(db: Session, user: User, plan: MealPlan, provider: Provider) -> int:
    """Describe the plan's dishes that have no current text; return how many got some.

    One provider call per MAX_DISHES_PER_CALL dishes, in name order. Each dish
    goes under an opaque reference ("d1", "d2", ...) that means something only
    within its call, and only a reference that was sent is read back. A dish
    whose description fails `clean` gets no row; a cooking note that fails is
    kept as null.

    Of the plan, this reads only which dishes it holds. It never writes a plan
    or a plan item.

    Raises crypto.NotConfigured when the server has no keyring (key_for checks
    that before it reads anything, so the answer does not depend on whether this
    user ever saved a key), NoKey when the user has no usable key, and lets a
    ProviderError through for the router to answer and roll back. Flushes; the
    router commits.
    """
    key = llm.key_for(db, user)
    if key is None:
        raise NoKey
    api_key, model = key

    dish_ids = set(db.scalars(select(MealPlanItem.dish_id).where(MealPlanItem.plan_id == plan.id)))
    described = current_polish(db, user, dish_ids)
    briefs = dish_briefs(db, dish_ids - set(described))
    # By name, then id, so the calls do not depend on the query plan.
    pending = sorted(briefs.items(), key=lambda entry: (entry[1][0], str(entry[0])))

    kept = 0
    for start in range(0, len(pending), MAX_DISHES_PER_CALL):
        batch = pending[start : start + MAX_DISHES_PER_CALL]
        sent = {f"d{number}": entry for number, entry in enumerate(batch, start=1)}
        answers = provider.polish(
            api_key,
            model,
            [
                DishBrief(ref=ref, name=name, ingredients=ingredients)
                for ref, (_, (name, ingredients)) in sent.items()
            ],
        )
        for ref, text in answers.items():
            if ref not in sent:
                continue
            description = clean(text.description)
            if description is None:
                continue
            dish_id, (name, ingredients) = sent[ref]
            _keep(
                db,
                user,
                dish_id,
                digest=brief_hash(name, ingredients),
                description=description,
                cooking_note=clean(text.cooking_note),
                model=model,
            )
            kept += 1
    db.flush()
    return kept


def _keep(
    db: Session,
    user: User,
    dish_id: uuid.UUID,
    *,
    digest: str,
    description: str,
    cooking_note: str | None,
    model: str,
) -> None:
    """Insert or replace this user's text for one dish, in one statement."""
    values = {
        "user_id": user.id,
        "dish_id": dish_id,
        "brief_hash": digest,
        "description": description,
        "cooking_note": cooking_note,
        "model": model,
    }
    statement = insert(DishPolish).values(**values)
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_dish_polish_user_dish",
            set_={
                name: statement.excluded[name]
                for name in values
                if name not in ("user_id", "dish_id")
            },
        )
    )
