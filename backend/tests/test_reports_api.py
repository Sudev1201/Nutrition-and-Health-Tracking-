"""The weekly report, end to end: the diary and the ledger in, one week's account out.

Dates run relative to the real today. A week is complete only once its Saturday
has ended, so LAST_WEEK -- the Sunday before this week's -- is the latest
complete week, and THIS_WEEK is in progress. A profile save records a weigh-in
dated today, which moves no target: one weigh-in is not a trend.

The fixture dish, Plain rice, carries 150 kcal, 4 g of protein and 30 mg of
calcium per 100 g and nothing else. Every other nutrient is unmeasured, so the
figures below follow from it by hand.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.diary import service as diary
from app.models.diary import MealLog
from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient, PortionMeasure
from app.models.nutrient import Nutrient
from app.models.plan import MealPlan, MealPlanItem
from app.models.user import User
from app.models.weight import CalorieAdjustment
from app.nutrition_core.energy import Body, energy_target
from app.planner import service as planner_service
from app.reports import service as reports
from tests.test_tracking_api import PROFILE, meal_times_with

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
THIS_WEEK = planner_service.week_start_for(TODAY)
LAST_WEEK = THIS_WEEK - datetime.timedelta(days=7)
NEXT_WEEK = THIS_WEEK + datetime.timedelta(days=7)

# The reference man's energy target. Only the one test that says so recalibrates it.
FORMULA_KCAL = energy_target(
    Body(sex="male", age=25, weight_kg=65.0, activity="sedentary"), goal="maintain", pace=None
)
# Protein is 0.83 g/kg, with 0.66 g/kg as its EAR.
PROTEIN_RDA = 65.0 * 0.83
PROTEIN_EAR = 65.0 * 0.66

VEG = "vegetarian eggetarian fishetarian veg"

# (code, name, per-100g nutrients, diet tags)
INGREDIENTS = [
    ("test:ragi", "Ragi flour", {"energy": 320, "protein": 7, "calcium": 344}, VEG),
    ("test:curd", "Curd, cow milk", {"energy": 60, "protein": 3, "calcium": 150}, VEG),
    ("test:egg", "Egg, whole",
     {"energy": 155, "protein": 13, "calcium": 50}, "eggetarian fishetarian"),
    ("test:urad", "Urad dal",
     {"energy": 340, "protein": 25, "calcium": 150, "potassium": 900}, VEG),
]

# (code, name, slot tags, diet tag, yield, [(ingredient, raw grams)], (default measure, grams))
DISHES = [
    ("test:ragi-mudde", "Ragi mudde", "lunch dinner", "vegetarian", 2.0,
     [("test:ragi", 100)], ("1 ball", 150)),
    ("test:curd-rice", "Curd rice", "lunch dinner", "vegetarian", 1.2,
     [("test:rice", 300), ("test:curd", 200)], ("1 cup", 200)),
    ("test:egg-curry", "Egg curry", "lunch dinner", "eggetarian", 1.0,
     [("test:egg", 200)], ("1 egg", 60)),
]


@pytest.fixture
def tracker(signed_in, reference_data):
    """A signed-in client with the reference man's profile."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    return signed_in


@pytest.fixture
def user(tracker, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


@pytest.fixture
def report_pool(db, reference_data) -> dict:
    """Three plannable dishes, and the ingredients they are made of, by code.

    Per default portion:
    - Ragi mudde (1 ball, 150 g): 258 mg calcium, 5.25 g protein.
    - Curd rice (1 cup, 200 g): 130 mg calcium, 6 g protein.
    - Egg curry (1 egg, 60 g): 30 mg calcium, 7.8 g protein. Never offered to a
      vegetarian.

    Urad dal is logged as it is. It is the only food here with potassium, at
    900 mg per 100 g.
    """
    nutrients = {n.code: n for n in db.scalars(select(Nutrient))}
    rows = {"test:rice": db.scalar(select(Ingredient).where(Ingredient.code == "test:rice"))}

    for code, name, values, tags in INGREDIENTS:
        ingredient = Ingredient(code=code, name=name, source="IFCT", diet_tags=tags)
        db.add(ingredient)
        db.flush()
        for nutrient_code, per_100g in values.items():
            db.add(
                IngredientNutrient(
                    ingredient_id=ingredient.id,
                    nutrient_id=nutrients[nutrient_code].id,
                    per_100g=per_100g,
                    source="IFCT",
                )
            )
        rows[code] = ingredient

    for code, name, slots, diet, yield_factor, recipe, (measure, grams) in DISHES:
        dish = Dish(
            code=code, name=name, source="authored", is_editable=True,
            slot_tags=slots, diet_tags=diet, yield_factor=yield_factor,
        )
        db.add(dish)
        db.flush()
        for ingredient_code, raw_grams in recipe:
            db.add(
                DishIngredient(
                    dish_id=dish.id, ingredient_id=rows[ingredient_code].id, grams=raw_grams
                )
            )
        db.add(
            PortionMeasure(dish_id=dish.id, measure_name=measure, grams=grams, is_default=True)
        )
        rows[code] = dish
    db.flush()
    return rows


def last_week(offset: int) -> datetime.date:
    return LAST_WEEK + datetime.timedelta(days=offset)


def report(api, start: datetime.date = LAST_WEEK) -> dict:
    response = api.get(f"/reports/week?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def log(
    api,
    food,
    on: datetime.date,
    slot: str,
    grams: float,
    *,
    kind: str = "dish",
    estimated: bool = False,
) -> None:
    created = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": slot, "food_id": str(food.id), "food_kind": kind,
            "grams": grams, "is_estimated": estimated,
        },
    )
    assert created.status_code == 201, created.text


def skip(api, on: datetime.date, slot: str) -> None:
    assert api.post("/diary/skips", json={"date": str(on), "slot": slot}).status_code == 201


def by_code(items: list[dict], key: str = "code") -> dict[str, dict]:
    return {item[key]: item for item in items}


def codes(week: dict) -> list[str]:
    return [s["nutrient_code"] for s in week["suggestions"]]


def names(suggestion: dict) -> list[str]:
    return [food["name"] for food in suggestion["foods"]]


def plan_for(db, owner: User, week_start: datetime.date, items) -> MealPlan:
    """A stored plan, written directly: the planner never plans a day already over."""
    plan = MealPlan(user_id=owner.id, week_start=week_start, seed=1)
    db.add(plan)
    db.flush()
    for day, slot, dish in items:
        db.add(
            MealPlanItem(
                plan_id=plan.id, plan_date=day, slot=slot, dish_id=dish.id, grams=200.0
            )
        )
    db.flush()
    return plan


def a_short_week(api, rice) -> None:
    """Three tracked days of too little last week, one of them eaten out.

    Sun  lunch 200 g              300 kcal  8 g protein  60 mg calcium; dinner skipped
    Mon  lunch 100 g, estimated   150 kcal  4 g          30 mg
    Wed  lunch 200 g              300 kcal  8 g          60 mg; lunch also skipped
    Fri  breakfast skipped, and nothing eaten
    """
    log(api, rice, last_week(0), "lunch", 200)
    skip(api, last_week(0), "dinner")
    log(api, rice, last_week(1), "lunch", 100, estimated=True)
    log(api, rice, last_week(3), "lunch", 200)
    skip(api, last_week(3), "lunch")
    skip(api, last_week(5), "breakfast")


# --- access ------------------------------------------------------------------------------


def test_the_report_needs_a_session(api_client):
    assert api_client.get(f"/reports/week?start={LAST_WEEK}").status_code == 401


def test_the_report_needs_a_profile(signed_in, reference_data):
    response = signed_in.get(f"/reports/week?start={LAST_WEEK}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Complete your profile first"


def test_a_report_week_starts_on_a_sunday(tracker):
    assert tracker.get(f"/reports/week?start={last_week(1)}").status_code == 422


def test_a_week_that_has_not_started_cannot_be_reported(tracker):
    assert tracker.get(f"/reports/week?start={NEXT_WEEK}").status_code == 422


# --- the week's shape ----------------------------------------------------------------------


def test_a_finished_week_runs_sunday_to_saturday(tracker):
    week = report(tracker)

    assert week["start_date"] == str(LAST_WEEK)
    assert week["end_date"] == str(last_week(6))
    assert week["status"] == "complete"
    assert [d["date"] for d in week["days"]] == [str(last_week(n)) for n in range(7)]
    assert [d["weekday"] for d in week["days"]] == [
        "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat",
    ]


def test_an_empty_week_is_untracked_rather_than_short(tracker):
    """A week the app was not used is silence, not seven days of eating nothing."""
    week = report(tracker)

    assert week["tracked_days"] == 0
    assert {d["state"] for d in week["days"]} == {"untracked"}
    assert week["slots"] == {"logged": 0, "skipped": 0, "expected": 35}
    assert week["nutrients"] == []
    assert week["uncompensated"] == []
    assert week["suggestions"] == []
    assert week["plan"] is None


def test_the_current_week_counts_only_the_days_that_have_ended(tracker, reference_data):
    log(tracker, reference_data, TODAY, "lunch", 200)

    week = report(tracker, THIS_WEEK)

    elapsed = (TODAY - THIS_WEEK).days
    states = [d["state"] for d in week["days"]]
    assert week["status"] == "in-progress"
    assert states[:elapsed] == ["untracked"] * elapsed
    assert states[elapsed] == "in-progress"
    assert states[elapsed + 1 :] == ["future"] * (6 - elapsed)
    # Today's lunch belongs to a day still being eaten, so it counts in nothing yet.
    assert week["tracked_days"] == 0
    assert week["measured_kcal"] == 0
    assert week["nutrients"] == []
    assert week["slots"] == {"logged": 0, "skipped": 0, "expected": 5 * elapsed}
    assert [d["energy_kcal"] for d in week["days"]] == [0] * 7
    assert [d["target_kcal"] for d in week["days"]] == [round(FORMULA_KCAL)] * 7


# --- days and meals ------------------------------------------------------------------------


def test_a_day_is_tracked_when_something_was_logged(tracker, reference_data):
    a_short_week(tracker, reference_data)

    week = report(tracker)

    # Friday held only a skip: something was said, but nothing eaten.
    assert [d["state"] for d in week["days"]] == [
        "tracked", "tracked", "untracked", "tracked", "untracked", "untracked", "untracked",
    ]
    assert week["tracked_days"] == 3


def test_every_meal_slot_of_the_week_is_accounted_for(tracker, reference_data):
    a_short_week(tracker, reference_data)

    # Five slots on each of seven days. Three lunches were logged -- Wednesday's
    # skip gives way to the food -- and two slots were skipped, Friday's on a day
    # with nothing eaten at all. The other thirty were missed.
    assert report(tracker)["slots"] == {"logged": 3, "skipped": 2, "expected": 35}


def test_a_snack_switched_off_is_not_expected(tracker, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    # Food eaten in it is still food, but a slot that is not expected is not
    # counted among the ones that are.
    log(tracker, reference_data, last_week(0), "snack1", 100)

    assert report(tracker)["slots"] == {"logged": 0, "skipped": 0, "expected": 28}


# --- energy ----------------------------------------------------------------------------------


def test_energy_eaten_out_is_kept_apart_from_measured_energy(tracker, reference_data):
    a_short_week(tracker, reference_data)

    week = report(tracker)

    # Sunday's and Wednesday's 300 kcal were weighed; Monday's 150 was estimated.
    assert week["measured_kcal"] == 600
    assert week["estimated_kcal"] == 150


def test_each_day_carries_its_energy_and_its_base_target(tracker, reference_data):
    a_short_week(tracker, reference_data)

    days = report(tracker)["days"]

    assert [d["energy_kcal"] for d in days] == [300, 150, 0, 300, 0, 0, 0]
    # The base target, before any carry. Sunday's shortfall raised Monday's
    # effective energy target, not the figure shown here.
    assert [d["target_kcal"] for d in days] == [round(FORMULA_KCAL)] * 7


def test_a_recalibration_mid_week_moves_only_the_days_from_it(tracker, user, db):
    db.add(
        CalorieAdjustment(
            user_id=user.id, effective_from=last_week(3), kind="step", offset_kcal=-210.0,
            reason="Your weight has risen about 0.5 kg a week.",
        )
    )
    db.flush()

    days = report(tracker)["days"]

    # Each day is costed at the target it had, not at the one in force now.
    assert [d["target_kcal"] for d in days[:3]] == [round(FORMULA_KCAL)] * 3
    assert [d["target_kcal"] for d in days[3:]] == [round(FORMULA_KCAL - 210)] * 4


# --- nutrients -------------------------------------------------------------------------------


def test_weekly_totals_count_only_the_days_that_measured_it(tracker, reference_data):
    a_short_week(tracker, reference_data)

    nutrients = by_code(report(tracker)["nutrients"])

    # Macros, then minerals. Potassium was never measured, so it is absent
    # rather than reported as a week of zeros.
    assert list(nutrients) == ["energy", "protein", "calcium"]
    assert nutrients["calcium"] == {
        "code": "calcium", "display_name": "Calcium", "unit": "mg",
        "category": "mineral", "kind": "target", "measured_days": 3,
        # Three days of the base target. Monday's effective target was 1,300 mg
        # after Sunday's carry, and summing that would count Sunday's shortfall
        # twice.
        "target_total": 3000.0, "ear_total": 2400.0, "consumed_total": 150.0,
        "days_met": 0, "days_over_limit": 0, "coverage": 1.0,
    }
    protein = nutrients["protein"]
    assert protein["target_total"] == pytest.approx(3 * PROTEIN_RDA, abs=0.06)
    assert protein["ear_total"] == pytest.approx(3 * PROTEIN_EAR, abs=0.06)
    assert protein["consumed_total"] == 20.0
    # Energy has no EAR at all.
    assert nutrients["energy"]["ear_total"] is None


def test_a_day_past_the_ear_is_met_and_a_day_past_the_limit_is_not(tracker, report_pool):
    curd = report_pool["test:curd"]
    log(tracker, curd, last_week(0), "lunch", 600, kind="ingredient")  # 900 mg calcium
    log(tracker, curd, last_week(1), "lunch", 1800, kind="ingredient")  # 2,700 mg

    calcium = by_code(report(tracker)["nutrients"])["calcium"]

    # 900 mg clears the 800 mg EAR. 2,700 mg is past the 2,500 mg upper limit,
    # which is never "met", however far past the target it is.
    assert calcium["days_met"] == 1
    assert calcium["days_over_limit"] == 1


# --- what could not be made up ---------------------------------------------------------------


def test_shortfalls_that_expired_are_reported_with_their_reason(tracker, reference_data):
    a_short_week(tracker, reference_data)

    gaps = by_code(report(tracker)["uncompensated"])

    # Energy expired too, and is left out on purpose: telling someone that
    # calories were "not made up" works against a weight goal.
    assert set(gaps) == {"protein", "calcium"}

    # Protein has no storage pool, so every short gram expired the day it happened.
    assert gaps["protein"]["reason_code"] == "not_compensable"
    assert gaps["protein"]["reason"] == (
        "Protein has no storage pool, so a short day is not carried forward."
    )
    assert gaps["protein"]["amount"] == pytest.approx(3 * PROTEIN_RDA - 20.0, abs=0.06)

    # A day carries at most 300 mg of calcium to each of the next two days.
    # - Sunday was 940 mg short, and 340 expired.
    # - Monday, owed 300, was 1,270 short, and 670 expired.
    # - Wednesday, owed Monday's second 300, was 1,240 short, and 640 expired.
    # Tuesday was untracked, so nothing was costed or expired there.
    assert gaps["calcium"] == {
        "code": "calcium", "display_name": "Calcium", "unit": "mg", "amount": 1650.0,
        "reason_code": "cap", "reason": "Beyond the 30% a day can carry, so it expired.",
    }


# --- suggestions -------------------------------------------------------------------------------


def test_suggestions_name_the_shortest_nutrients_first(tracker, reference_data):
    a_short_week(tracker, reference_data)

    suggestions = report(tracker)["suggestions"]

    # Calcium reached 5% of its week and protein 12%. Energy is never suggested.
    assert [s["nutrient_code"] for s in suggestions] == ["calcium", "protein"]
    # The fixture dish carries no slot tags, so there is no pool to suggest from.
    assert suggestions[0] == {
        "nutrient_code": "calcium",
        "display_name": "Calcium",
        "text": "Calcium fell short this week.",
        "foods": [],
    }


def test_suggestions_name_dishes_rich_in_the_nutrient(tracker, reference_data, report_pool):
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    # Best first, per default portion. Egg curry is never offered to a vegetarian.
    assert names(suggestions["calcium"]) == ["Ragi mudde", "Curd rice"]
    assert names(suggestions["protein"]) == ["Curd rice", "Ragi mudde"]
    first = suggestions["calcium"]["foods"][0]
    assert first["food_id"] == str(report_pool["test:ragi-mudde"].id)
    assert suggestions["calcium"]["text"].startswith("Calcium fell short this week.")


def test_suggested_dishes_follow_the_diet(tracker, reference_data, report_pool):
    tracker.put("/profile", json={**PROFILE, "diet_type": "eggetarian"})
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    # 7.8 g of protein in an egg's curry, 6 g in a cup of curd rice, 5.25 g in a ball of ragi.
    assert names(suggestions["protein"]) == ["Egg curry", "Curd rice", "Ragi mudde"]


def test_suggested_dishes_leave_out_avoided_foods(tracker, reference_data, report_pool):
    curd_rice = report_pool["test:curd-rice"]
    avoided = [{"label": "Curd rice", "food_id": str(curd_rice.id), "food_kind": "dish"}]
    tracker.put("/profile", json={**PROFILE, "avoided": avoided})
    a_short_week(tracker, reference_data)

    suggestions = by_code(report(tracker)["suggestions"], key="nutrient_code")

    assert names(suggestions["calcium"]) == ["Ragi mudde"]
    assert names(suggestions["protein"]) == ["Ragi mudde"]


def test_potassium_is_never_pushed_on_a_potassium_sparing_drug(tracker, report_pool):
    """Spec manual step 7b. The drug already raises potassium, and more is unsafe."""
    urad = report_pool["test:urad"]
    for offset in range(3):
        log(tracker, urad, last_week(offset), "lunch", 100, kind="ingredient")
    # 450 of 3,000 mg calcium, 2,700 of 10,530 mg potassium, 75 of ~162 g protein.
    assert codes(report(tracker)) == ["calcium", "potassium", "protein"]

    tracker.put(
        "/profile",
        json={
            **PROFILE,
            "conditions": ["hypertension"],
            "medications": [{"name": "Losartan", "time": "08:00"}],
        },
    )

    # The report is derived on demand, so it reads the profile as it is now.
    assert codes(report(tracker)) == ["calcium", "protein"]


# --- the plan ----------------------------------------------------------------------------------


def test_plan_adherence_counts_the_slots_eaten_as_planned(
    tracker, user, db, reference_data, report_pool
):
    rice, curd_rice = reference_data, report_pool["test:curd-rice"]
    plan_for(
        db,
        user,
        LAST_WEEK,
        [
            (last_week(0), "lunch", rice),  # eaten as planned
            (last_week(0), "dinner", curd_rice),  # something else eaten
            (last_week(1), "lunch", curd_rice),  # nothing logged
        ],
    )
    log(tracker, rice, last_week(0), "lunch", 200)
    log(tracker, rice, last_week(0), "dinner", 200)

    assert report(tracker)["plan"] == {"planned": 3, "followed": 1}


def test_plan_items_on_days_not_yet_over_count_for_nothing(tracker, user, db, reference_data):
    plan_for(db, user, THIS_WEEK, [(TODAY, "lunch", reference_data)])

    # A plan exists, so the figure is there -- with nothing in it yet.
    assert report(tracker, THIS_WEEK)["plan"] == {"planned": 0, "followed": 0}


# --- privacy -----------------------------------------------------------------------------------


def test_another_users_diary_and_plan_never_appear(tracker, db, reference_data):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    for offset in range(7):
        db.add(
            MealLog(
                user_id=other.id, logged_on=last_week(offset), slot="lunch",
                dish_id=reference_data.id, grams=400.0, portion_label="400 g",
            )
        )
    plan_for(db, other, LAST_WEEK, [(last_week(0), "lunch", reference_data)])

    week = report(tracker)

    assert week["tracked_days"] == 0
    assert week["measured_kcal"] == 0
    assert week["slots"]["logged"] == 0
    assert week["nutrients"] == []
    assert week["plan"] is None


# --- the diary's shared readers ------------------------------------------------------------


def test_a_days_breakdown_agrees_with_the_diary_totals(
    tracker, user, db, reference_data, report_pool
):
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    log(tracker, reference_data, day, "snack2", 100, estimated=True)
    log(tracker, report_pool["test:urad"], day, "dinner", 50, kind="ingredient")

    breakdown = diary.day_breakdown(db, user, day)

    assert breakdown.consumed == pytest.approx(diary.consumed_on(db, user, day))
    assert breakdown.coverage == pytest.approx(diary.coverage_on(db, user, day))
    # Only the dal carries potassium: 50 g of the day's 350 g.
    assert breakdown.coverage["potassium"] == pytest.approx(50 / 350)
    assert breakdown.estimated_energy == pytest.approx(150.0)
    assert breakdown.logged_slots == frozenset({"lunch", "snack2", "dinner"})


def test_a_day_with_nothing_logged_breaks_down_to_nothing(user, db):
    assert diary.day_breakdown(db, user, last_week(2)) == diary.DayBreakdown(
        consumed={}, coverage={}, estimated_energy=0.0, logged_slots=frozenset()
    )


def test_slot_states_follow_the_diary_rules(tracker, user, db, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    skip(tracker, day, "lunch")  # food wins over a skip
    skip(tracker, day, "dinner")
    skip(tracker, day, "snack1")  # switched off and empty: left out, skipped or not

    assert list(diary.slot_states(db, user, day).items()) == [
        ("breakfast", "empty"),
        ("lunch", "logged"),
        ("snack2", "empty"),
        ("dinner", "skipped"),
    ]


def test_a_slot_switched_off_still_shows_food_eaten_in_it(tracker, user, db, reference_data):
    tracker.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})
    log(tracker, reference_data, last_week(2), "snack1", 100)

    assert diary.slot_states(db, user, last_week(2))["snack1"] == "logged"


def test_the_diary_screen_shows_the_same_slot_states(tracker, user, db, reference_data):
    day = last_week(2)
    log(tracker, reference_data, day, "lunch", 200)
    skip(tracker, day, "dinner")

    screen = tracker.get(f"/diary?date={day}").json()

    assert [(s["slot"], s["state"]) for s in screen["slots"]] == list(
        diary.slot_states(db, user, day).items()
    )


# --- what the next plan is told --------------------------------------------------------------


def test_the_next_plan_hears_what_the_report_suggests(tracker, user, db, reference_data):
    a_short_week(tracker, reference_data)

    suggested = reports.suggested_codes(db, user, LAST_WEEK, TODAY)

    assert suggested == ["calcium", "protein"]
    week = reports.build_week(db, user, LAST_WEEK, TODAY)
    assert suggested == [s.nutrient_code for s in week.suggestions]


def test_two_tracked_days_are_too_few_to_steer_the_next_plan(tracker, user, db, reference_data):
    log(tracker, reference_data, last_week(0), "lunch", 200)
    log(tracker, reference_data, last_week(1), "lunch", 200)

    assert reports.suggested_codes(db, user, LAST_WEEK, TODAY) == []


def test_a_week_not_yet_started_suggests_nothing(user, db):
    assert reports.suggested_codes(db, user, NEXT_WEEK, TODAY) == []
