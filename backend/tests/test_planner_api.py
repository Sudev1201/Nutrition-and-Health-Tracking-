"""The meal planner, end to end: profile -> plan -> swap, lock, regenerate, re-plan.

Builds its own small pool on top of `reference_data`, so every assertion here is
about the planner's behaviour rather than about which of 72 seeded dishes won a
near-tie. Dates are in the coming week: the planner never plans a day that has
already ended, so a fixed date in the past would come back empty.
"""

import datetime
import uuid
import zoneinfo

import pytest
from sqlalchemy import select

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient, PortionMeasure
from app.models.household import HouseholdMember
from app.models.nutrient import Nutrient
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.planner import service as planner
from app.profiles import service as profiles
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")

# A week that has not started yet, so every day of it can be planned.
def upcoming_sunday() -> datetime.date:
    today = datetime.datetime.now(KOLKATA).date()
    days = (6 - today.weekday()) % 7
    return today + datetime.timedelta(days=days or 7)


WEEK = upcoming_sunday()
MONDAY = WEEK + datetime.timedelta(days=1)
FRIDAY = WEEK + datetime.timedelta(days=5)

VEG = "vegetarian eggetarian fishetarian veg"

# (code, name, per-100g nutrients, diet tags)
INGREDIENTS = [
    ("test:urad", "Urad dal",
     {"energy": 340, "protein": 25, "calcium": 150, "potassium": 900}, VEG),
    ("test:curd", "Curd, cow milk",
     {"energy": 60, "protein": 3, "calcium": 150, "vitamin_b12": 0.4}, VEG),
    ("test:egg", "Egg, whole",
     {"energy": 155, "protein": 13, "calcium": 50, "vitamin_b12": 1.1}, "eggetarian fishetarian"),
    ("test:chicken", "Chicken, meat",
     {"energy": 240, "protein": 27, "potassium": 250}, None),
    ("test:chana", "Bengal gram, whole",
     {"energy": 160, "protein": 9, "calcium": 50, "fibre": 8}, VEG),
    ("test:milk", "Milk, cow",
     {"energy": 60, "protein": 3, "calcium": 120, "vitamin_b12": 0.5}, VEG),
]

# (code, name, slot tags, diet tag, yield, [(ingredient code, raw grams)], [(measure, grams)])
DISHES = [
    ("test:idli", "Idli", "breakfast snack dinner", "vegetarian", 2.6,
     [("test:rice", 400), ("test:urad", 100)], [("1 idli", 45), ("3 idli", 135)]),
    ("test:sambar-rice", "Rice with sambar", "lunch dinner", "vegetarian", 2.5,
     [("test:rice", 300), ("test:urad", 100)], [("1 cup", 200)]),
    ("test:curd-rice", "Curd rice", "lunch dinner", "vegetarian", 1.2,
     [("test:rice", 300), ("test:curd", 200)], [("1 cup", 200)]),
    ("test:egg-curry", "Egg curry", "lunch dinner", "eggetarian", 1.0,
     [("test:egg", 200)], [("1 egg", 60)]),
    ("test:chicken-curry", "Chicken curry", "lunch dinner", "nonveg", 1.0,
     [("test:chicken", 300)], [("1 cup", 150)]),
    ("test:sundal", "Chana sundal", "snack", "vegetarian", 1.0,
     [("test:chana", 200)], [("1 katori", 100)]),
    ("test:coffee", "Filter coffee", "breakfast snack", "vegetarian", 1.0,
     [("test:milk", 150)], [("1 tumbler", 150)]),
]


@pytest.fixture
def planner_pool(db, reference_data) -> dict[str, Dish]:
    """Seven dishes across every slot, one egg, one meat, one calcium-heavy drink."""
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    ingredients = {
        "test:rice": db.scalar(select(Ingredient).where(Ingredient.code == "test:rice"))
    }

    for code, name, values, tags in INGREDIENTS:
        ingredient = Ingredient(code=code, name=name, source="IFCT", diet_tags=tags)
        db.add(ingredient)
        db.flush()
        for nutrient_code, per_100g in values.items():
            db.add(IngredientNutrient(
                ingredient_id=ingredient.id, nutrient_id=nutrients[nutrient_code].id,
                per_100g=per_100g, source="IFCT",
            ))
        ingredients[code] = ingredient

    dishes = {}
    for code, name, slots, diet, yield_factor, recipe, measures in DISHES:
        dish = Dish(
            code=code, name=name, source="authored", is_editable=True,
            slot_tags=slots, diet_tags=diet, yield_factor=yield_factor,
        )
        db.add(dish)
        db.flush()
        for ingredient_code, grams in recipe:
            db.add(DishIngredient(
                dish_id=dish.id, ingredient_id=ingredients[ingredient_code].id, grams=grams,
            ))
        for index, (measure, grams) in enumerate(measures):
            db.add(PortionMeasure(
                dish_id=dish.id, measure_name=measure, grams=grams, is_default=(index == 0),
            ))
        dishes[code] = dish
    db.flush()
    return dishes


NON_VEG_PROFILE = {**PROFILE, "diet_type": "non-vegetarian"}


def week(api, start=WEEK):
    response = api.get(f"/plan/week?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def day_of(plan: dict, date: datetime.date) -> dict:
    return next(d for d in plan["days"] if d["date"] == str(date))


def item_in(plan: dict, date: datetime.date, slot: str) -> dict | None:
    return next((i for i in day_of(plan, date)["items"] if i["slot"] == slot), None)


def _user(db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


# --- shape and lifecycle ---------------------------------------------------------------


def test_the_plan_needs_a_profile(signed_in, planner_pool):
    assert signed_in.get(f"/plan/week?start={WEEK}").status_code == 404


def test_the_week_must_start_on_a_sunday(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    assert signed_in.get(f"/plan/week?start={MONDAY}").status_code == 422


def test_a_week_is_generated_on_first_request_sunday_to_saturday(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    plan = week(signed_in)

    assert plan["start_date"] == str(WEEK)
    assert [d["weekday"] for d in plan["days"]] == [
        "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    ]
    for day in plan["days"]:
        assert [i["slot"] for i in day["items"]] == [
            "breakfast", "snack1", "lunch", "snack2", "dinner",
        ]
        for item in day["items"]:
            assert item["dish_name"]
            assert item["portion"]
            assert item["locked"] is False


def test_asking_again_returns_the_stored_plan_not_a_new_one(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    first = week(signed_in)
    second = week(signed_in)

    assert [i["id"] for d in first["days"] for i in d["items"]] == [
        i["id"] for d in second["days"] for i in d["items"]
    ]


def test_portions_read_as_household_measures(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    portions = {i["portion"] for d in week(signed_in)["days"] for i in d["items"]}

    # Every portion is a count of a seeded measure -- "3 idli", "1½ cup" -- never bare grams.
    assert portions
    assert all(not p.endswith(" g") for p in portions)


def test_days_that_have_already_ended_are_not_planned(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    today = datetime.datetime.now(KOLKATA).date()
    this_week = planner.week_start_for(today)

    plan = week(signed_in, this_week)

    for day in plan["days"]:
        date = datetime.date.fromisoformat(day["date"])
        if date < today:
            assert day["items"] == []
        else:
            assert day["items"]


def test_an_empty_pool_gives_an_empty_but_valid_week(signed_in, reference_data):
    # `reference_data` seeds one dish with no slot tags, so nothing is plannable.
    signed_in.put("/profile", json=NON_VEG_PROFILE)

    plan = week(signed_in)

    assert len(plan["days"]) == 7
    assert all(day["items"] == [] for day in plan["days"])


# --- constraints -----------------------------------------------------------------------------


def test_a_friday_rule_makes_friday_vegetarian_and_says_so(signed_in, planner_pool):
    signed_in.put(
        "/profile",
        json={
            **PROFILE,
            "diet_type": "eggetarian",
            "observances": [{"kind": "weekday", "weekday": 5, "label": ""}],
        },
    )

    plan = week(signed_in)
    friday = day_of(plan, FRIDAY)
    monday = day_of(plan, MONDAY)

    assert friday["vegetarian"] is True
    assert friday["vegetarian_reason"] == "your Friday rule"
    assert all(i["dish_name"] != "Egg curry" for i in friday["items"])
    assert monday["vegetarian"] is False
    assert monday["vegetarian_reason"] is None


def test_a_vegetarian_never_sees_egg_or_meat(signed_in, planner_pool):
    signed_in.put("/profile", json={**PROFILE, "diet_type": "vegetarian"})

    names = {i["dish_name"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "Egg curry" not in names
    assert "Chicken curry" not in names


def test_an_avoided_dish_is_never_suggested(signed_in, planner_pool):
    curd_rice = planner_pool["test:curd-rice"]
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "avoided": [
                {"label": "Curd rice", "food_id": str(curd_rice.id), "food_kind": "dish"}
            ],
        },
    )

    names = {i["dish_name"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "Curd rice" not in names


def test_a_disabled_snack_slot_is_not_planned(signed_in, planner_pool):
    meal_times = [
        {**slot, "is_enabled": slot["slot"] != "snack1"} for slot in PROFILE["meal_times"]
    ]
    signed_in.put("/profile", json={**NON_VEG_PROFILE, "meal_times": meal_times})

    slots = {i["slot"] for d in week(signed_in)["days"] for i in d["items"]}

    assert "snack1" not in slots
    assert "snack2" in slots


def test_a_skipped_meal_is_not_planned_for_that_day(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    signed_in.post("/diary/skips", json={"date": str(MONDAY), "slot": "dinner"})

    plan = week(signed_in)

    assert item_in(plan, MONDAY, "dinner") is None
    assert item_in(plan, MONDAY + datetime.timedelta(days=1), "dinner") is not None


# --- medication ------------------------------------------------------------------------


def test_calcium_heavy_food_stays_four_hours_clear_of_levothyroxine(signed_in, planner_pool):
    # Breakfast at 08:00 is one hour after the dose: inside the four-hour window,
    # so the milk coffee (180 mg calcium a tumbler) is refused there and idli is
    # the only breakfast left. Lunch at 13:30 is clear, so curd rice may appear.
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "conditions": ["hypothyroidism"],
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
        },
    )

    plan = week(signed_in)

    breakfasts = {
        i["dish_name"] for d in plan["days"] for i in d["items"] if i["slot"] == "breakfast"
    }
    assert breakfasts == {"Idli"}


def test_breakfast_inside_the_sixty_minute_window_says_when_to_eat(signed_in, planner_pool):
    meal_times = [
        {**slot, "time": "07:30"} if slot["slot"] == "breakfast" else slot
        for slot in PROFILE["meal_times"]
    ]
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "meal_times": meal_times,
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
        },
    )

    breakfast = item_in(week(signed_in), MONDAY, "breakfast")

    assert breakfast is not None
    assert "08:00" in breakfast["rationale"]


def test_potassium_is_not_pushed_for_a_hypertensive_on_an_ace_inhibitor(
    signed_in, planner_pool, db
):
    signed_in.put(
        "/profile",
        json={
            **NON_VEG_PROFILE,
            "conditions": ["hypertension"],
            "medications": [{"name": "Ramipril", "time": "08:00"}],
        },
    )
    user = _user(db)

    context = planner.build_context(db, user, profiles.get_profile(db, user), MONDAY)

    # The baseline AI, not hypertension's 4,000 mg: raising potassium is unsafe
    # on ramipril, and the planner inherits that from the targets overlay.
    assert context.goals["potassium"].amount == 3510


def test_warfarin_holds_vitamin_k_steady_in_the_planner(signed_in, planner_pool, db):
    signed_in.put(
        "/profile",
        json={**NON_VEG_PROFILE, "medications": [{"name": "Warfarin", "time": "20:00"}]},
    )
    user = _user(db)

    context = planner.build_context(db, user, profiles.get_profile(db, user), MONDAY)

    assert context.hold_steady == frozenset({"vitamin_k"})


# --- editing the plan -------------------------------------------------------------------


def test_locking_survives_regeneration(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")

    locked = signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True})
    assert locked.status_code == 200
    assert item_in(locked.json(), MONDAY, "lunch")["locked"] is True

    regenerated = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)})
    assert regenerated.status_code == 200

    kept = item_in(regenerated.json(), MONDAY, "lunch")
    assert kept["id"] == lunch["id"]
    assert kept["dish_id"] == lunch["dish_id"]
    assert kept["locked"] is True

    unlocked = signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": False})
    assert item_in(unlocked.json(), MONDAY, "lunch")["locked"] is False


def test_regenerating_replaces_the_unlocked_items(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = {i["id"] for d in week(signed_in)["days"] for i in d["items"]}

    after_plan = signed_in.post("/plan/week/regenerate", json={"start": str(WEEK)}).json()
    after = {i["id"] for d in after_plan["days"] for i in d["items"]}

    assert before.isdisjoint(after)
    assert len(after) == len(before)


def test_swapping_replaces_only_that_dish(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    plan = week(signed_in)
    lunch = item_in(plan, MONDAY, "lunch")
    dinner = item_in(plan, MONDAY, "dinner")

    swapped = signed_in.post(f"/plan/items/{lunch['id']}/swap", json={})
    assert swapped.status_code == 200, swapped.text

    new_lunch = item_in(swapped.json(), MONDAY, "lunch")
    assert new_lunch["dish_id"] != lunch["dish_id"]
    assert item_in(swapped.json(), MONDAY, "dinner") == dinner


def test_a_locked_item_cannot_be_swapped(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    lunch = item_in(week(signed_in), MONDAY, "lunch")
    signed_in.patch(f"/plan/items/{lunch['id']}", json={"locked": True})

    assert signed_in.post(f"/plan/items/{lunch['id']}/swap", json={}).status_code == 409


def test_someone_elses_item_is_not_found(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    week(signed_in)

    assert signed_in.patch(f"/plan/items/{uuid.uuid4()}", json={"locked": True}).status_code == 404


# --- deviation: re-plan the rest of the day ----------------------------------------------


def log(api, dish: Dish, on: datetime.date, slot: str) -> None:
    created = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": slot, "food_id": str(dish.id),
            "food_kind": "dish", "grams": 200, "is_estimated": False,
        },
    )
    assert created.status_code == 201, created.text


def test_logging_something_off_plan_replans_only_the_rest_of_that_day(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    planned_lunch = item_in(before, MONDAY, "lunch")
    off_plan = next(
        d for d in planner_pool.values()
        if str(d.id) != planned_lunch["dish_id"] and "lunch" in d.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")
    after = week(signed_in)

    # Earlier slots and the logged slot itself keep their rows.
    for slot in ("breakfast", "snack1", "lunch"):
        assert item_in(after, MONDAY, slot) == item_in(before, MONDAY, slot)
    # Later slots are re-planned around what was actually eaten.
    for slot in ("snack2", "dinner"):
        assert item_in(after, MONDAY, slot)["id"] != item_in(before, MONDAY, slot)["id"]
    # Every other day is untouched.
    for day in before["days"]:
        if day["date"] != str(MONDAY):
            assert day_of(after, datetime.date.fromisoformat(day["date"])) == day


def test_logging_the_planned_dish_changes_nothing(signed_in, planner_pool, db):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    planned = item_in(before, MONDAY, "lunch")
    dish = db.get(Dish, uuid.UUID(planned["dish_id"]))

    log(signed_in, dish, MONDAY, "lunch")

    assert week(signed_in) == before


def test_a_locked_dinner_survives_an_off_plan_lunch(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    before = week(signed_in)
    dinner = item_in(before, MONDAY, "dinner")
    signed_in.patch(f"/plan/items/{dinner['id']}", json={"locked": True})
    planned_lunch = item_in(before, MONDAY, "lunch")
    off_plan = next(
        d for d in planner_pool.values()
        if str(d.id) != planned_lunch["dish_id"] and "lunch" in d.slot_tags
    )

    log(signed_in, off_plan, MONDAY, "lunch")

    kept = item_in(week(signed_in), MONDAY, "dinner")
    assert kept["id"] == dinner["id"]
    assert kept["locked"] is True


# --- the household cooking view -------------------------------------------------------------


def test_a_solo_user_has_no_cooking_overlaps(signed_in, planner_pool):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    week(signed_in)

    response = signed_in.get(f"/plan/cooking?date={MONDAY}")

    assert response.status_code == 200
    assert response.json() == {"date": str(MONDAY), "overlaps": []}


def test_the_cooking_view_names_members_whose_plans_share_a_dish(signed_in, planner_pool, db):
    signed_in.put("/profile", json=NON_VEG_PROFILE)
    household = signed_in.post("/households", json={"name": "Home"}).json()
    mine = item_in(week(signed_in), MONDAY, "lunch")

    amma = User(google_sub="sub-amma", email="amma@example.com", name="Amma")
    db.add(amma)
    db.flush()
    db.add(HouseholdMember(household_id=uuid.UUID(household["id"]), user_id=amma.id))
    plan = MealPlan(user_id=amma.id, week_start=WEEK, seed=1)
    db.add(plan)
    db.flush()
    db.add(MealPlanItem(
        plan_id=plan.id, plan_date=MONDAY, slot="lunch",
        dish_id=uuid.UUID(mine["dish_id"]), grams=200.0, measure_name="cup", quantity=1.0,
    ))
    # A second item that cannot coincide: sundal is never a breakfast candidate,
    # so the signed-in user's breakfast is idli or coffee and this stays unshared.
    db.add(MealPlanItem(
        plan_id=plan.id, plan_date=MONDAY, slot="breakfast",
        dish_id=planner_pool["test:sundal"].id, grams=100.0, measure_name="katori", quantity=1.0,
    ))
    db.flush()

    overlaps = signed_in.get(f"/plan/cooking?date={MONDAY}").json()["overlaps"]

    assert overlaps == [
        {"slot": "lunch", "dish_name": mine["dish_name"], "members": ["Amma", "Tracker"]},
    ]
