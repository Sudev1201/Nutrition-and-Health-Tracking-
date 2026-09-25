"""AI descriptions on the plan, end to end: what is sent, what is kept, what never moves.

`POST /plan/week/polish` is the only route that calls a model, and all it may
add is two strings per dish. These tests hold it to that. The plan's rows and
every planner field are snapshotted around it, the SQL it runs is watched, and
the fake provider's inputs are read back to prove the model is shown dish and
ingredient names and nothing else.

The provider is conftest's `FakeProvider`, which records every call as
`(api_key, model, briefs)`. Unless a test sets `texts`, it answers every dish
with "A home-style <name>.", which passes the guard.
"""

import dataclasses
import datetime
import re
import uuid

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import delete, select

from app.config import settings
from app.llm.providers import (
    DishBrief,
    DishText,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    ProviderUnavailable,
)
from app.models.food import Dish, DishIngredient, Ingredient
from app.models.household import HouseholdMember
from app.models.llm import DishPolish
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.planner import polish
from tests.conftest import sql_statements
from tests.test_planner_api import (
    MONDAY,
    NON_VEG_PROFILE,
    WEEK,
    build_planner_pool,
    item_in,
    log,
    week,
)
from tests.test_tracking_api import PROFILE

# Obviously fake, and never printed: see `save_key` and the privacy test.
KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
POLISH_FIELDS = ("description", "cooking_note")
NO_KEY = "Add your Anthropic API key under AI descriptions first"
# Beside a polish's 200: how many dishes that request stored new text for.
DESCRIBED = "X-Dishes-Described"
# An INSERT, UPDATE or DELETE that names either of the plan's tables.
PLAN_WRITE = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE)\b.*\bmeal_plan(s|_items)\b", re.IGNORECASE | re.DOTALL
)


@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """test_planner_api's seven dishes across every slot, one egg, one meat."""
    return build_planner_pool(db)


# --- helpers -----------------------------------------------------------------------------


def me(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


def save_key(api, model: str = "claude-opus-5") -> None:
    saved = api.put("/settings/llm", json={"api_key": KEY, "model": model})
    # The detail only: whatever went wrong, the key stays out of the failure output.
    assert saved.status_code == 200, saved.json().get("detail")


def planned(api, profile: dict = NON_VEG_PROFILE, model: str = "claude-opus-5") -> dict:
    """A saved profile and key, and the coming week's plan, generated."""
    assert api.put("/profile", json=profile).status_code == 200
    save_key(api, model)
    return week(api)


def polish_week(api, start: datetime.date = WEEK):
    return api.post("/plan/week/polish", json={"start": str(start)})


def described(api, start: datetime.date = WEEK) -> dict:
    response = polish_week(api, start)
    assert response.status_code == 200, response.json().get("detail")
    return response.json()


def calls_made(fake) -> int:
    """How many polish calls the fake saw. Counted in a helper, so a failing assert
    prints a number, never the recorded calls, whose first element is the key."""
    return len(fake.polished)


def items(plan: dict) -> list[dict]:
    return [item for day in plan["days"] for item in day["items"]]


def without_polish(plan: dict) -> dict:
    """The plan as the planner made it: every field but the two AI ones."""
    return {
        **plan,
        "days": [
            {
                **day,
                "items": [
                    {key: value for key, value in item.items() if key not in POLISH_FIELDS}
                    for item in day["items"]
                ],
            }
            for day in plan["days"]
        ],
    }


def home_style(name: str) -> str:
    """FakeProvider's answer for a dish when a test sets no `texts`."""
    return f"A home-style {name}."


def stored_plan(db) -> tuple[list, list]:
    """Every stored column polish could conceivably move, read from the tables."""
    user_id = me(db).id
    plans = db.execute(
        select(MealPlan.id, MealPlan.week_start, MealPlan.seed, MealPlan.emphasis)
        .where(MealPlan.user_id == user_id)
        .order_by(MealPlan.week_start)
    ).all()
    rows = db.execute(
        select(
            MealPlanItem.id,
            MealPlanItem.plan_id,
            MealPlanItem.plan_date,
            MealPlanItem.slot,
            MealPlanItem.dish_id,
            MealPlanItem.grams,
            MealPlanItem.measure_name,
            MealPlanItem.quantity,
            MealPlanItem.locked,
            MealPlanItem.rationale,
        )
        .join(MealPlan, MealPlan.id == MealPlanItem.plan_id)
        .where(MealPlan.user_id == user_id)
        .order_by(MealPlanItem.id)
    ).all()
    return plans, rows


def polish_rows(db) -> dict[uuid.UUID, tuple[str, str | None, str]]:
    """This user's stored descriptions: dish id -> (description, cooking note, model)."""
    rows = db.execute(
        select(
            DishPolish.dish_id, DishPolish.description, DishPolish.cooking_note, DishPolish.model
        ).where(DishPolish.user_id == me(db).id)
    ).all()
    return {row.dish_id: (row.description, row.cooking_note, row.model) for row in rows}


def ingredient_names(db, dish_id: uuid.UUID) -> tuple[str, ...]:
    return tuple(
        sorted(
            db.scalars(
                select(Ingredient.name)
                .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
                .where(DishIngredient.dish_id == dish_id)
            )
        )
    )


def fail_on_second_call(fake, error: type[Exception]) -> list[int]:
    """Answer the first call as usual, then raise `error`. Returns each call's size.

    So a failure always lands after rows were written, and the test can see
    that they went too.
    """
    sizes: list[int] = []
    answer = fake.polish

    def polish_then_fail(api_key, model, dishes):
        sizes.append(len(dishes))
        if len(sizes) > 1:
            raise error
        return answer(api_key, model, dishes)

    fake.polish = polish_then_fail
    return sizes


# --- the fields ----------------------------------------------------------------------------


def test_a_plan_shows_no_descriptions_until_asked(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    plan = planned(signed_in)

    assert items(plan)
    for item in items(plan):
        # Present and null. A field on ItemView but not on PlanItemOut would be
        # dropped without an error, so the JSON itself is checked.
        assert item["description"] is None
        assert item["cooking_note"] is None


def test_descriptions_arrive_on_the_week_and_stay_there(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)

    polished = described(signed_in)

    for item in items(polished):
        assert item["description"] == home_style(item["dish_name"])
        assert item["cooking_note"] is None
    with sql_statements(db) as seen:
        assert week(signed_in) == polished
    # Reading the week shows cached text; it never looks at the key.
    assert not [statement for statement in seen if "user_settings" in statement]


def test_generating_reading_and_editing_the_plan_never_call_a_model(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in)
    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})
    assert regenerated.status_code == 200
    lunch = item_in(regenerated.json(), MONDAY, "lunch")
    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 200
    swapped = item_in(week(signed_in), MONDAY, "lunch")
    assert signed_in.patch(f"/plan/items/{swapped['id']}", json={"locked": True}).status_code == 200
    off_plan = next(
        dish
        for dish in planner_pool.values()
        if str(dish.id) != swapped["dish_id"] and "lunch" in dish.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")
    week(signed_in)

    assert calls_made(fake_provider) == 0


# --- nothing in the plan moves ---------------------------------------------------------------

HOSTILE = (
    DishText("Use 500 g of rice", "Double the dal for more protein."),
    DishText("Swap it for pongal", "Skip the rice and serve it with pongal instead."),
    DishText("Covers 90% of your calcium", None),
    DishText("A soft, comforting everyday dish.", "Serve it hot."),
)


def test_polish_moves_nothing_in_the_plan(signed_in, planner_pool, llm_keyring, fake_provider, db):
    """The spec: polish never changes a dish, a portion, a rationale or a number."""
    before = planned(signed_in)
    assert len({item["dish_id"] for item in items(before)}) >= len(HOSTILE)
    stored = stored_plan(db)
    fake_provider.texts = {
        f"d{number}": HOSTILE[(number - 1) % len(HOSTILE)]
        for number in range(1, polish.MAX_DISHES_PER_CALL + 1)
    }

    with sql_statements(db) as seen:
        response = polish_week(signed_in)

    assert response.status_code == 200
    # Every field the planner owns reads as it did, in the answer and afterwards.
    assert without_polish(response.json()) == without_polish(before)
    assert without_polish(week(signed_in)) == without_polish(before)
    # So does every stored column, row for row, and the plan's seed.
    assert stored_plan(db) == stored
    # No write was even attempted against the plan's tables...
    assert [statement for statement in seen if PLAN_WRITE.match(statement)] == []
    # ...while the listener was live: the descriptions themselves were written.
    assert any(
        statement.lstrip().upper().startswith("INSERT INTO DISH_POLISH") for statement in seen
    )
    # ...and nothing else was written at all: the text is the only thing stored, so no
    # dish, recipe, measure or nutrient row can move either.
    writes = [s for s in seen if re.match(r"\s*(INSERT|UPDATE|DELETE)\b", s, re.IGNORECASE)]
    assert writes
    assert [s for s in writes if not s.lstrip().upper().startswith("INSERT INTO DISH_POLISH")] == []
    # Text that passes the guard is shown however it is worded, and only as text.
    polished = items(response.json())
    assert "Swap it for pongal" in {item["description"] for item in polished}
    assert {item["description"] for item in polished} <= {
        None,
        "Swap it for pongal",
        "A soft, comforting everyday dish.",
    }
    assert {item["cooking_note"] for item in polished} <= {
        None,
        "Skip the rice and serve it with pongal instead.",
        "Serve it hot.",
    }


# --- the guard -------------------------------------------------------------------------------


def test_only_text_that_passes_the_guard_is_kept(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    plan = planned(signed_in)
    assert len({item["dish_id"] for item in items(plan)}) >= 5
    fake_provider.texts = {
        "d1": DishText("Use 500 g of rice", "Serve it hot."),
        "d2": DishText("Covers 90% of your calcium", None),
        "d3": DishText("Rich in protein and fibre", "Serve it hot."),
        "d4": DishText("  A soft steamed rice cake.  ", "Rest the batter overnight."),
        "d5": DishText("A tangy lentil stew.", "Add two cups of water."),
    }

    polished = described(signed_in)

    sent = {brief.ref: brief.name for brief in fake_provider.polished[0][2]}
    shown = {
        item["dish_name"]: (item["description"], item["cooking_note"]) for item in items(polished)
    }
    # A failing description leaves the dish undescribed, whatever its note said.
    for ref in ("d1", "d2", "d3"):
        assert shown[sent[ref]] == (None, None), ref
    assert shown[sent["d4"]] == ("A soft steamed rice cake.", "Rest the batter overnight.")
    # A failing note goes on its own; the description stands.
    assert shown[sent["d5"]] == ("A tangy lentil stew.", None)
    # A dish the answer left out stays undescribed.
    for ref, name in sent.items():
        if ref not in fake_provider.texts:
            assert shown[name] == (None, None), ref
    # Only the two kept dishes have rows, each naming the model that wrote it.
    rows = polish_rows(db)
    assert {db.get(Dish, dish_id).name for dish_id in rows} == {sent["d4"], sent["d5"]}
    assert {model for _, _, model in rows.values()} == {"claude-opus-5"}


def test_a_note_naming_a_household_measure_is_stored_as_null(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    fake_provider.texts = {
        "d1": DishText(
            "A soft steamed rice cake.", "Have a bowl of it with a glass of buttermilk."
        ),
        "d2": DishText("A Glass of cold buttermilk.", "Serve it chilled."),
        "d3": DishText("A tangy lentil stew.", "Break the papad into PIECES over it."),
    }

    polished = described(signed_in)

    sent = {brief.ref: brief.name for brief in fake_provider.polished[0][2]}
    shown = {
        item["dish_name"]: (item["description"], item["cooking_note"]) for item in items(polished)
    }
    # The description stands, and the failing note is stored as null.
    assert shown[sent["d1"]] == ("A soft steamed rice cake.", None)
    assert shown[sent["d3"]] == ("A tangy lentil stew.", None)
    # A description naming a measure leaves the dish undescribed.
    assert shown[sent["d2"]] == (None, None)
    rows = polish_rows(db)
    assert {db.get(Dish, dish_id).name: row[:2] for dish_id, row in rows.items()} == {
        sent["d1"]: ("A soft steamed rice cake.", None),
        sent["d3"]: ("A tangy lentil stew.", None),
    }


def test_an_answer_for_a_reference_that_was_not_sent_is_dropped(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    stray = DishText("A dish nobody asked about.", None)
    fake_provider.texts = {
        "d1": DishText("A soft steamed rice cake.", None),
        "d99": stray,
        "D2": stray,
        " d3": stray,
    }

    polished = described(signed_in)

    sent = {brief.ref: brief.name for brief in fake_provider.polished[0][2]}
    assert "d99" not in sent
    shown = {item["dish_name"]: item["description"] for item in items(polished)}
    assert shown == {
        name: ("A soft steamed rice cake." if ref == "d1" else None) for ref, name in sent.items()
    }
    assert [db.get(Dish, dish_id).name for dish_id in polish_rows(db)] == [sent["d1"]]


def test_an_empty_answer_leaves_the_week_undescribed_and_is_not_an_error(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    """What the service sees when the model refused, or ran out of tokens."""
    plan = planned(signed_in)
    fake_provider.texts = {}

    response = polish_week(signed_in)

    assert response.status_code == 200
    assert response.json() == plan
    # A 200 all the same. The count is how a client tells it from success.
    assert response.headers[DESCRIBED] == "0"
    assert polish_rows(db) == {}
    # Nothing was stored, so asking again sends the same dishes again.
    described(signed_in)
    assert calls_made(fake_provider) == 2
    assert fake_provider.polished[1][2] == fake_provider.polished[0][2]


# --- what the model is shown -----------------------------------------------------------------


def test_the_model_is_shown_dish_and_ingredient_names_and_nothing_else(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    urad = db.scalar(select(Ingredient).where(Ingredient.code == "test:urad"))
    breakfast_soon_after_the_dose = [
        {**slot, "time": "07:30"} if slot["slot"] == "breakfast" else slot
        for slot in PROFILE["meal_times"]
    ]
    plan = planned(
        signed_in,
        profile={
            **NON_VEG_PROFILE,
            "meal_times": breakfast_soon_after_the_dose,
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
            # Named the way the user would, not the way IFCT does.
            "favourites": [{"label": "Ulundu", "food_id": str(urad.id), "food_kind": "ingredient"}],
        },
    )
    # The rationale carries what must stay here: the medication and its timing,
    # the favourite in the user's own word, and usually a percentage.
    rationales = [item["rationale"] for item in items(plan) if item["rationale"]]
    assert "levothyroxine" in item_in(plan, MONDAY, "breakfast")["rationale"]
    assert any("Ulundu" in text for text in rationales)

    described(signed_in)

    # A brief has room for nothing but a reference and two kinds of name.
    assert [field.name for field in dataclasses.fields(DishBrief)] == [
        "ref",
        "name",
        "ingredients",
    ]
    [(api_key, model, briefs)] = fake_provider.polished
    # Compared outside the assert, so a failure cannot print the key.
    sent_the_saved_key = api_key == KEY
    assert sent_the_saved_key
    assert model == "claude-opus-5"
    # Every dish in the plan, once: its name and its ingredients' names, sorted.
    dishes = {item["dish_id"]: item["dish_name"] for item in items(plan)}
    assert len(briefs) == len(dishes)
    assert {brief.name: brief.ingredients for brief in briefs} == {
        name: ingredient_names(db, uuid.UUID(dish_id)) for dish_id, name in dishes.items()
    }
    words = "\n".join(text for brief in briefs for text in (brief.name, *brief.ingredients))
    assert "levothyroxine" not in words.lower()
    assert "Ulundu" not in words
    assert not re.search(r"[\d%]", words)
    for text in rationales:
        assert text not in words


def test_dishes_go_out_in_name_order_a_batch_at_a_time(
    signed_in, planner_pool, llm_keyring, fake_provider, monkeypatch
):
    plan = planned(signed_in, model="claude-sonnet-5")
    monkeypatch.setattr(polish, "MAX_DISHES_PER_CALL", 3)

    polished = described(signed_in)

    calls = fake_provider.polished
    names = sorted({item["dish_name"] for item in items(plan)})
    assert [brief.name for _, _, briefs in calls for brief in briefs] == names
    assert [len(briefs) for _, _, briefs in calls] == [
        min(3, len(names) - start) for start in range(0, len(names), 3)
    ]
    # References start again in every call, and mean nothing outside it.
    for _, _, briefs in calls:
        assert [brief.ref for brief in briefs] == [f"d{n}" for n in range(1, len(briefs) + 1)]
    # The model is the one the user chose.
    assert {model for _, model, _ in calls} == {"claude-sonnet-5"}
    assert all(item["description"] for item in items(polished))


# --- the cache -------------------------------------------------------------------------------


def test_a_described_dish_is_not_sent_again(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)
    first = described(signed_in)

    second = described(signed_in)

    assert calls_made(fake_provider) == 1
    assert second == first


def test_the_answer_says_how_many_dishes_got_text(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    plan = planned(signed_in)
    dishes = len({item["dish_id"] for item in items(plan)})
    assert dishes > 0

    first = polish_week(signed_in)
    second = polish_week(signed_in)

    assert first.status_code == 200
    assert second.status_code == 200
    # The body is the week, as every plan route answers it; the count rides beside it.
    assert first.headers[DESCRIBED] == str(dishes)
    # Everything is cached now: nothing was sent, and nothing is new.
    assert second.headers[DESCRIBED] == "0"
    assert calls_made(fake_provider) == 1


def test_a_page_on_the_frontend_origin_can_read_the_count(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in)

    response = signed_in.post(
        "/plan/week/polish",
        json={"start": str(WEEK)},
        headers={"Origin": settings.frontend_origin},
    )

    assert response.status_code == 200
    # The Plan screen is served from another origin, and fetch hands a script only
    # the response headers that CORS lists as exposed.
    exposed = response.headers["access-control-expose-headers"]
    assert DESCRIBED.lower() in {name.strip().lower() for name in exposed.split(",")}


def test_renaming_an_ingredient_makes_its_dishes_stale_and_they_go_out_again(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    first = described(signed_in)
    lunch = item_in(first, MONDAY, "lunch")
    ingredient = db.scalars(
        select(Ingredient)
        .join(DishIngredient, DishIngredient.ingredient_id == Ingredient.id)
        .where(DishIngredient.dish_id == uuid.UUID(lunch["dish_id"]))
        .order_by(Ingredient.name)
    ).first()
    uses = set(
        db.scalars(
            select(DishIngredient.dish_id).where(DishIngredient.ingredient_id == ingredient.id)
        )
    )
    stale = {uuid.UUID(item["dish_id"]) for item in items(first)} & uses
    assert uuid.UUID(lunch["dish_id"]) in stale

    # What a re-seed that renames an IFCT food looks like to the cache.
    ingredient.name = "Renamed by a re-seed"
    db.flush()

    # The model was shown the old name, so those dishes' text stops showing...
    for item in items(week(signed_in)):
        stale_dish = uuid.UUID(item["dish_id"]) in stale
        assert item["description"] == (None if stale_dish else home_style(item["dish_name"]))
    fake_provider.texts = {
        f"d{number}": DishText("Described again.", None)
        for number in range(1, polish.MAX_DISHES_PER_CALL + 1)
    }

    again = described(signed_in)

    # ...and only they go out again, under the new name, and their new text shows.
    assert calls_made(fake_provider) == 2
    resent = fake_provider.polished[1][2]
    assert {brief.name for brief in resent} == {db.get(Dish, dish_id).name for dish_id in stale}
    assert all("Renamed by a re-seed" in brief.ingredients for brief in resent)
    for item in items(again):
        stale_dish = uuid.UUID(item["dish_id"]) in stale
        expected = "Described again." if stale_dish else home_style(item["dish_name"])
        assert item["description"] == expected


def test_the_week_shows_the_rows_text_not_a_stale_object_held_in_the_session(
    signed_in, planner_pool, llm_keyring, fake_provider, db, monkeypatch
):
    """current_polish reads columns, so an upsert's new text shows at once.

    The upsert is a Core statement, which never refreshes a DishPolish object the
    session already holds, and neither session expires on commit. Read as ORM
    objects, the week would get the held object back, with its old text and old
    fingerprint, and show nothing for the dish.
    """
    planned(signed_in)
    lunch = item_in(described(signed_in), MONDAY, "lunch")
    held = db.scalar(
        select(DishPolish).where(
            DishPolish.user_id == me(db).id,
            DishPolish.dish_id == uuid.UUID(lunch["dish_id"]),
        )
    )
    assert held.description == home_style(lunch["dish_name"])
    # A new prompt makes every cached text stale, so the next polish rewrites every row.
    monkeypatch.setattr(polish, "PROMPT_VERSION", polish.PROMPT_VERSION + 1)
    fake_provider.texts = {
        f"d{number}": DishText("Described again.", None)
        for number in range(1, polish.MAX_DISHES_PER_CALL + 1)
    }

    again = described(signed_in)

    # The row itself was rewritten, while the object held in the session was not.
    assert polish_rows(db)[held.dish_id][0] == "Described again."
    assert held.description == home_style(lunch["dish_name"])
    # The week shows the row's new text, in the polish answer and on a later read.
    assert item_in(again, MONDAY, "lunch")["description"] == "Described again."
    assert item_in(week(signed_in), MONDAY, "lunch")["description"] == "Described again."


def test_a_swapped_in_dish_shows_its_own_text_never_the_old_ones(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    lunch = item_in(described(signed_in), MONDAY, "lunch")
    assert lunch["description"] == home_style(lunch["dish_name"])
    # Keep only the outgoing dish's text, so the incoming dish has none of its own.
    db.execute(
        delete(DishPolish).where(
            DishPolish.user_id == me(db).id,
            DishPolish.dish_id != uuid.UUID(lunch["dish_id"]),
        )
    )
    db.flush()

    swapped = signed_in.post(f"/plan/items/{lunch['id']}/swap", json={})

    assert swapped.status_code == 200, swapped.text
    new_lunch = item_in(swapped.json(), MONDAY, "lunch")
    # The same plan item, updated in place, now holding another dish. The text
    # follows the dish, so the item has none.
    assert new_lunch["id"] == lunch["id"]
    assert new_lunch["dish_id"] != lunch["dish_id"]
    assert new_lunch["description"] is None
    assert new_lunch["cooking_note"] is None
    # The outgoing dish keeps its text wherever else it appears.
    for item in items(swapped.json()):
        if item["dish_id"] == lunch["dish_id"]:
            assert item["description"] == home_style(lunch["dish_name"])

    # Described now, the incoming dish gets its own.
    again = item_in(described(signed_in), MONDAY, "lunch")
    assert again["description"] == home_style(new_lunch["dish_name"])


def test_regenerating_keeps_each_dishs_text(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)
    polished = described(signed_in)
    lunch = item_in(polished, MONDAY, "lunch")
    assert signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True}).status_code == 200
    described_dishes = {item["dish_id"] for item in items(polished)}

    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})

    assert regenerated.status_code == 200
    after = items(regenerated.json())
    # New rows for every unlocked slot...
    unlocked_before = {item["id"] for item in items(polished)} - {lunch["id"]}
    unlocked_after = {item["id"] for item in after} - {lunch["id"]}
    assert unlocked_before.isdisjoint(unlocked_after)
    # ...and still the text, because it belongs to the dish, not the row.
    for item in after:
        expected = home_style(item["dish_name"]) if item["dish_id"] in described_dishes else None
        assert item["description"] == expected
    assert any(item["id"] != lunch["id"] and item["description"] for item in after)
    kept = item_in(regenerated.json(), MONDAY, "lunch")
    assert kept["id"] == lunch["id"]
    assert kept["description"] == lunch["description"]
    # Regenerating asked the model nothing.
    assert calls_made(fake_provider) == 1


# --- the service, directly -------------------------------------------------------------------


def test_polish_week_counts_the_dishes_it_described(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    plan_json = planned(signed_in)
    user = me(db)
    plan = db.scalar(
        select(MealPlan).where(MealPlan.user_id == user.id, MealPlan.week_start == WEEK)
    )

    assert polish.polish_week(db, user, plan, fake_provider) == len(
        {item["dish_id"] for item in items(plan_json)}
    )
    # Everything is described now, so a second run has nothing to send.
    assert polish.polish_week(db, user, plan, fake_provider) == 0
    assert calls_made(fake_provider) == 1


def test_a_brief_is_the_dish_name_and_its_ingredient_names_sorted(db, planner_pool):
    idli = planner_pool["test:idli"]
    urad = db.scalar(select(Ingredient).where(Ingredient.code == "test:urad"))
    # The same ingredient twice in a recipe is still one name.
    db.add(DishIngredient(dish_id=idli.id, ingredient_id=urad.id, grams=10.0))
    bare = Dish(
        code="test:buttermilk",
        name="Buttermilk",
        source="authored",
        is_editable=True,
        yield_factor=1.0,
    )
    db.add(bare)
    db.flush()

    briefs = polish.dish_briefs(db, [idli.id, bare.id, idli.id])

    assert briefs == {
        idli.id: ("Idli", ("Rice, cooked", "Urad dal")),
        bare.id: ("Buttermilk", ()),
    }
    assert polish.dish_briefs(db, []) == {}


def test_cached_text_counts_only_for_its_owner_and_while_it_matches(signed_in, planner_pool, db):
    user = me(db)
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    idli, coffee, sundal = (
        planner_pool[code] for code in ("test:idli", "test:coffee", "test:sundal")
    )
    db.add_all(
        [
            DishPolish(
                user_id=user.id,
                dish_id=idli.id,
                brief_hash=polish.brief_hash("Idli", ("Rice, cooked", "Urad dal")),
                description="Soft steamed rice cakes.",
                cooking_note="Rest the batter overnight.",
                model="claude-opus-5",
            ),
            # Written from a brief that no longer matches the dish.
            DishPolish(
                user_id=user.id,
                dish_id=coffee.id,
                brief_hash="0" * 64,
                description="Strong and milky.",
                cooking_note=None,
                model="claude-opus-5",
            ),
            # Someone else's text, current, for a dish this user has none for.
            DishPolish(
                user_id=other.id,
                dish_id=sundal.id,
                brief_hash=polish.brief_hash("Chana sundal", ("Bengal gram, whole",)),
                description="Their sundal.",
                cooking_note=None,
                model="claude-opus-5",
            ),
        ]
    )
    db.flush()

    assert polish.current_polish(db, user, [idli.id, coffee.id, sundal.id]) == {
        idli.id: DishText("Soft steamed rice cakes.", "Rest the batter overnight."),
    }
    assert polish.current_polish(db, user, []) == {}


# --- when it cannot run ----------------------------------------------------------------------


def test_without_a_saved_key_polish_answers_409_and_calls_nothing(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    assert signed_in.put("/profile", json=NON_VEG_PROFILE).status_code == 200
    plan = week(signed_in)

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == 0
    assert week(signed_in) == plan


def test_a_server_without_a_keyring_answers_503(
    signed_in, planner_pool, fake_provider, set_keyring
):
    # Explicit, so a keyring in a developer's .env cannot turn the feature on here.
    set_keyring()
    assert signed_in.put("/profile", json=NON_VEG_PROFILE).status_code == 200
    week(signed_in)

    response = polish_week(signed_in)

    assert response.status_code == 503
    assert response.json()["detail"] == "AI descriptions are not set up on this server"
    assert calls_made(fake_provider) == 0


def test_a_saved_key_is_not_used_once_the_keyring_is_gone(
    signed_in, planner_pool, llm_keyring, fake_provider, set_keyring
):
    planned(signed_in)
    set_keyring()

    response = polish_week(signed_in)

    assert response.status_code == 503
    assert calls_made(fake_provider) == 0


def test_a_key_this_server_can_no_longer_read_is_marked_and_refused(
    signed_in, planner_pool, llm_keyring, fake_provider, db, set_keyring
):
    planned(signed_in)
    # Another keyring altogether: the stored token no longer decrypts.
    set_keyring(Fernet.generate_key().decode())

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == 0
    # The handler committed the mark. The shared test session would show a merely
    # flushed one too, but in production an uncommitted mark is rolled back when the
    # request's session closes; only a commit leaves no transaction open here.
    assert not db.in_transaction()
    assert signed_in.get("/settings/llm").json()["status"] == "unreadable"


@pytest.mark.parametrize(
    ("error", "code", "detail"),
    [
        pytest.param(
            KeyRejected,
            409,
            "Anthropic refused your saved key. Replace it under AI descriptions.",
            id="key-rejected",
        ),
        pytest.param(
            ModelUnavailable,
            409,
            "Your Anthropic account can't use Claude Opus 5. "
            "Choose another model under AI descriptions.",
            id="model-unavailable",
        ),
        pytest.param(NoCredit, 409, "Your Anthropic account has no credit left.", id="no-credit"),
        pytest.param(
            ProviderUnavailable,
            502,
            "Couldn't reach Anthropic. Your plan is unchanged.",
            id="unreachable",
        ),
    ],
)
def test_a_provider_failure_keeps_nothing_and_leaves_the_plan(
    error, code, detail, signed_in, planner_pool, llm_keyring, fake_provider, db, monkeypatch
):
    plan = planned(signed_in)
    stored = stored_plan(db)
    # Two dishes a call, and the second call fails: the first call's rows must go too.
    monkeypatch.setattr(polish, "MAX_DISHES_PER_CALL", 2)
    calls = fail_on_second_call(fake_provider, error)

    response = polish_week(signed_in)

    assert response.status_code == code
    assert response.json()["detail"] == detail
    assert calls == [2, 2]
    assert polish_rows(db) == {}
    assert stored_plan(db) == stored
    assert week(signed_in) == plan


def test_a_refused_key_is_marked_and_not_tried_again(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    fake_provider.error = KeyRejected()

    refused = polish_week(signed_in)

    assert refused.status_code == 409
    # Committed, as above: a 401 from Anthropic should not be met again next time.
    assert not db.in_transaction()
    assert signed_in.get("/settings/llm").json()["status"] == "rejected"
    calls = calls_made(fake_provider)
    again = polish_week(signed_in)
    assert again.status_code == 409
    assert again.json()["detail"] == NO_KEY
    assert calls_made(fake_provider) == calls


def test_the_model_message_names_the_users_own_model(
    signed_in, planner_pool, llm_keyring, fake_provider
):
    planned(signed_in, model="claude-haiku-4-5")
    fake_provider.error = ModelUnavailable()

    response = polish_week(signed_in)

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Your Anthropic account can't use Claude Haiku 4.5. "
        "Choose another model under AI descriptions."
    )


def test_polish_needs_a_sunday(signed_in, planner_pool, llm_keyring, fake_provider):
    planned(signed_in)

    response = polish_week(signed_in, MONDAY)

    assert response.status_code == 422
    assert response.json()["detail"] == "The plan week starts on a Sunday"


def test_polish_needs_a_plan_for_that_week(signed_in, planner_pool, llm_keyring, fake_provider, db):
    planned(signed_in)

    response = polish_week(signed_in, WEEK + datetime.timedelta(days=7))

    assert response.status_code == 404
    assert response.json()["detail"] == "There is no plan for that week yet"
    assert calls_made(fake_provider) == 0
    # Asking to describe a week never plans it.
    plans, _ = stored_plan(db)
    assert [row.week_start for row in plans] == [WEEK]


def test_polish_needs_a_session(api_client):
    assert api_client.post("/plan/week/polish", json={"start": str(WEEK)}).status_code == 401


# --- the household ---------------------------------------------------------------------------


def test_the_household_cooking_view_carries_no_ai_text(
    signed_in, planner_pool, llm_keyring, fake_provider, db
):
    planned(signed_in)
    household = signed_in.post("/households", json={"name": "Home"}).json()
    mine = item_in(described(signed_in), MONDAY, "lunch")
    assert mine["description"]
    amma = User(google_sub="sub-amma", email="amma@example.com", name="Amma")
    db.add(amma)
    db.flush()
    db.add(HouseholdMember(household_id=uuid.UUID(household["id"]), user_id=amma.id))
    plan = MealPlan(user_id=amma.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    db.add(
        MealPlanItem(
            plan_id=plan.id,
            plan_date=MONDAY,
            slot="lunch",
            dish_id=uuid.UUID(mine["dish_id"]),
            grams=200.0,
            measure_name="cup",
            quantity=1.0,
        )
    )
    db.flush()

    with sql_statements(db) as seen:
        response = signed_in.get(f"/plan/cooking?date={MONDAY}")

    # The three shared fields and nothing else: no description crosses over.
    assert response.json()["overlaps"] == [
        {"slot": "lunch", "dish_name": mine["dish_name"], "members": ["Amma", "Tracker"]},
    ]
    # Nor does that path read anyone's key or anyone's cached text.
    assert seen
    assert not [s for s in seen if re.search(r"\b(dish_polish|user_settings)\b", s)]
