"""The planner's construction and search, on a synthetic pool.

These pin the behaviours the spec asks for -- fills every slot, closes the
weighted gap, varies the week, honours locks, plans around what was eaten --
without any database. Numbers are chosen so each test has one obvious answer.
"""

import datetime
import itertools
import random
import uuid
from dataclasses import replace

import pytest

from app.planner.engine import (
    EMPHASIS_FACTOR,
    DayInput,
    NutrientGoal,
    PlannedItem,
    add_totals,
    alternative_for,
    day_cost,
    energy_budget,
    plan_day,
    plan_week,
    portion_for,
    weighted_gap,
)
from app.planner.rules import Candidate, FoodRef, Portion

MONDAY = datetime.date(2026, 8, 17)


def candidate(
    name: str,
    slots: set[str],
    energy: float,
    protein: float = 0.0,
    calcium: float = 0.0,
    vitamin_k: float = 0.0,
    grams: tuple[float, ...] = (100.0, 150.0, 200.0, 300.0),
    ingredients: tuple[str, ...] = (),
) -> Candidate:
    return Candidate(
        dish_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset(slots),
        diet="vegetarian",
        ingredient_ids=frozenset(uuid.uuid5(uuid.NAMESPACE_DNS, i) for i in ingredients),
        ingredient_names=ingredients,
        per_100g={
            "energy": energy, "protein": protein, "calcium": calcium, "vitamin_k": vitamin_k,
        },
        portions=tuple(Portion(g, "cup", g / 100.0, f"{g / 100.0:g} cup") for g in grams),
        default_grams=grams[0],
    )


GOALS = {
    "energy": NutrientGoal("energy", "Energy", 2000.0, "target"),
    "protein": NutrientGoal("protein", "Protein", 60.0, "target"),
    "calcium": NutrientGoal("calcium", "Calcium", 1000.0, "target", tul=2500.0),
    "sodium": NutrientGoal("sodium", "Sodium", 2000.0, "ceiling"),
    "vitamin_k": NutrientGoal("vitamin_k", "Vitamin K", 55.0, "target"),
}

IDLI = candidate("Idli", {"breakfast", "dinner"}, energy=130, protein=4, calcium=10)
DAL_RICE = candidate("Dal rice", {"lunch", "dinner"}, energy=150, protein=6, calcium=20)
# Calcium is deliberately its standout: 300 g covers 27% of the calcium goal
# against 15% of protein, so the rationale test has one right answer.
CURD_RICE = candidate("Curd rice", {"lunch", "dinner"}, energy=120, protein=3, calcium=90)
KEERAI = candidate("Keerai rice", {"lunch", "dinner"}, energy=140, protein=5, vitamin_k=120)
SUNDAL = candidate("Sundal", {"snack1", "snack2"}, energy=160, protein=9, calcium=50)
COFFEE = candidate("Filter coffee", {"snack1", "snack2"}, energy=60, protein=3, calcium=120)

MAIN_POOL = (IDLI, DAL_RICE, CURD_RICE, KEERAI, SUNDAL, COFFEE)


def slots_from(pool, slots=("breakfast", "snack1", "lunch", "snack2", "dinner")):
    return {slot: tuple(c for c in pool if slot in c.slots) for slot in slots}


def day(**overrides) -> DayInput:
    base = {"date": MONDAY, "goals": GOALS, "slots": slots_from(MAIN_POOL)}
    return DayInput(**{**base, **overrides})


def rng(seed: int = 1) -> random.Random:
    return random.Random(seed)


# --- the cost function -----------------------------------------------------------


def test_a_target_below_its_goal_costs_and_above_it_costs_nothing():
    goals = {"protein": GOALS["protein"]}

    assert weighted_gap({"protein": 30.0}, goals) == pytest.approx(2.0 * 0.5)
    assert weighted_gap({"protein": 90.0}, goals) == 0.0


def test_a_ceiling_costs_only_when_exceeded():
    goals = {"sodium": GOALS["sodium"]}

    assert weighted_gap({"sodium": 1500.0}, goals) == 0.0
    assert weighted_gap({"sodium": 3000.0}, goals) > 0.0


def test_breaching_the_upper_limit_is_penalised_hard():
    goals = {"calcium": GOALS["calcium"]}

    assert weighted_gap({"calcium": 3000.0}, goals) > weighted_gap({"calcium": 0.0}, goals)


def test_holding_a_nutrient_steady_penalises_a_swing_from_yesterday():
    steady = day(hold_steady=frozenset({"vitamin_k"}), previous_day={"vitamin_k": 50.0})

    level = day_cost({"vitamin_k": 55.0}, steady)
    swung = day_cost({"vitamin_k": 150.0}, steady)

    assert swung > level


# --- portions ----------------------------------------------------------------------


def test_the_portion_closest_to_the_energy_budget_is_chosen():
    # Dal rice is 150 kcal/100 g: 200 g is 300 kcal, 300 g is 450 kcal.
    assert portion_for(DAL_RICE, 320.0).grams == 200.0
    assert portion_for(DAL_RICE, 420.0).grams == 300.0


def test_the_energy_budget_shares_what_is_left_over_the_open_slots():
    # 2000 kcal, nothing placed: lunch is 30% of the day.
    all_slots = ["breakfast", "snack1", "lunch", "snack2", "dinner"]
    assert energy_budget(day(), "lunch", {}, all_slots) == pytest.approx(600.0)
    # 800 kcal already eaten and only lunch and dinner open: 1200 left, split 30:25.
    assert energy_budget(day(), "lunch", {"energy": 800.0}, ["lunch", "dinner"]) == pytest.approx(
        1200.0 * 30 / 55
    )


# --- one day -----------------------------------------------------------------------


def test_every_open_slot_is_filled_from_its_own_candidates():
    items = plan_day(day(), rng())

    assert [item.slot for item in items] == ["breakfast", "snack1", "lunch", "snack2", "dinner"]
    for item in items:
        allowed = {c.dish_id for c in day().slots[item.slot]}
        assert item.dish_id in allowed


def test_a_slot_with_no_candidates_is_left_empty_rather_than_invented():
    items = plan_day(day(slots={"lunch": (), "dinner": (DAL_RICE,)}), rng())

    assert [item.slot for item in items] == ["dinner"]


def test_the_same_seed_gives_the_same_plan():
    first = plan_day(day(), rng(7))
    second = plan_day(day(), rng(7))

    assert [(i.dish_id, i.portion.grams) for i in first] == [
        (i.dish_id, i.portion.grams) for i in second
    ]


def test_the_plan_beats_doing_nothing_and_never_repeats_a_dish_within_a_day():
    planned = plan_day(day(), rng())
    totals = add_totals(*(item.nutrients for item in planned))

    assert day_cost(totals, day()) < day_cost({}, day())
    assert len({item.dish_id for item in planned}) == len(planned)


def test_food_already_eaten_shrinks_what_is_planned():
    hungry = plan_day(day(), rng(3))
    fed = plan_day(day(consumed={"energy": 1200.0, "protein": 40.0}), rng(3))

    assert sum(i.nutrients["energy"] for i in fed) < sum(i.nutrients["energy"] for i in hungry)


def test_a_dish_already_eaten_today_is_not_offered_while_anything_else_fits():
    # Dal rice was eaten off-plan at lunch, so the re-planned dinner takes the
    # other candidate. Counting what a meal contributed is not enough on its own:
    # the engine has to know which dish it was.
    items = plan_day(
        day(slots={"dinner": (DAL_RICE, CURD_RICE)}, eaten=frozenset({DAL_RICE.dish_id})), rng()
    )

    assert [item.dish_id for item in items] == [CURD_RICE.dish_id]


def test_a_slot_whose_only_candidate_was_eaten_is_still_filled():
    # The same judgement as the repeat fallback: a pool too small to avoid the
    # dish eaten earlier is better than a hole in the day. This is why "eaten"
    # is an exclusion the engine can release, not a filter on the candidates --
    # a slot whose tuple arrived empty would be dropped without a word.
    items = plan_day(
        day(slots={"dinner": (DAL_RICE,)}, eaten=frozenset({DAL_RICE.dish_id})), rng()
    )

    assert [(item.slot, item.dish_id) for item in items] == [("dinner", DAL_RICE.dish_id)]


def test_a_locked_item_is_kept_and_its_slot_is_not_planned_again():
    locked = PlannedItem(
        slot="lunch",
        dish_id=CURD_RICE.dish_id,
        dish_name="Curd rice",
        portion=CURD_RICE.portions[2],
        nutrients={"energy": 240.0, "protein": 8.0, "calcium": 130.0},
        locked=True,
    )
    open_slots = {s: c for s, c in slots_from(MAIN_POOL).items() if s != "lunch"}

    items = plan_day(day(slots=open_slots, fixed=(locked,)), rng())

    assert "lunch" not in {item.slot for item in items}
    assert CURD_RICE.dish_id not in {item.dish_id for item in items}


def test_the_rationale_names_the_nutrient_a_dish_does_most_for():
    # Curd rice is the only lunch dish carrying real calcium against a 1000 mg goal.
    items = plan_day(day(slots={"lunch": (CURD_RICE,)}), rng())

    assert items[0].rationale is not None
    assert "calcium" in items[0].rationale.lower()


def test_a_favourite_is_mentioned_when_a_dish_carries_it():
    with_curd = candidate("Curd rice", {"lunch"}, energy=120, ingredients=("Curd", "Rice"))
    items = plan_day(
        day(slots={"lunch": (with_curd,)}, favourites=(FoodRef("Curd"),)), rng()
    )

    assert items[0].favourites == ("Curd",)
    assert "curd" in (items[0].rationale or "").lower()


def test_no_rationale_is_invented_for_an_unremarkable_dish():
    plain = candidate("Plain rice", {"lunch"}, energy=130, grams=(50.0,))
    items = plan_day(day(slots={"lunch": (plain,)}), rng())

    assert items[0].rationale is None


# --- the week --------------------------------------------------------------------------


def test_a_week_does_not_serve_the_same_dinner_every_night():
    days = [day(date=MONDAY + datetime.timedelta(days=n)) for n in range(7)]

    week = plan_week(days, rng(11))
    dinners = [next(i.dish_id for i in items if i.slot == "dinner") for items in week]

    assert len(set(dinners)) > 1


def test_a_held_steady_nutrient_stays_level_across_the_week():
    # Keerai is the only source of vitamin K. With nothing held, the planner
    # reaches for it whenever calcium and protein allow; with warfarin, the
    # swing between consecutive days must stay inside the tolerance.
    days = [
        day(date=MONDAY + datetime.timedelta(days=n), hold_steady=frozenset({"vitamin_k"}))
        for n in range(4)
    ]

    week = plan_week(days, rng(5))
    vitamin_k = [sum(i.nutrients["vitamin_k"] for i in items) for items in week]

    swings = [
        abs(b - a) / GOALS["vitamin_k"].amount for a, b in itertools.pairwise(vitamin_k)
    ]
    assert max(swings) <= 0.25 + 1e-9 or all(v == vitamin_k[0] for v in vitamin_k)


# --- swapping ------------------------------------------------------------------------


def test_the_alternative_for_a_slot_is_a_different_dish_that_fits():
    current = plan_day(day(), rng())
    lunch = next(i for i in current if i.slot == "lunch")
    others = tuple(i for i in current if i.slot != "lunch")

    swapped = alternative_for(
        day(slots={"lunch": slots_from(MAIN_POOL)["lunch"]}, fixed=others),
        "lunch",
        rng(2),
        exclude=frozenset({lunch.dish_id}),
    )

    assert swapped is not None
    assert swapped.slot == "lunch"
    assert swapped.dish_id != lunch.dish_id
    assert swapped.dish_id not in {i.dish_id for i in others}


def test_no_alternative_when_every_other_candidate_is_excluded():
    assert alternative_for(
        day(slots={"lunch": (DAL_RICE,)}), "lunch", rng(), exclude=frozenset({DAL_RICE.dish_id})
    ) is None


# --- emphasis: what last week's report found short -------------------------------------


def test_an_emphasised_target_weighs_its_shortfall_more():
    plain = {"calcium": GOALS["calcium"]}
    # Calcium's usual weight is 1.5; emphasised, it is 1.5 x 1.5.
    stressed = {"calcium": replace(GOALS["calcium"], weight=1.5 * EMPHASIS_FACTOR)}

    # Half the goal is a relative shortfall of 0.5.
    assert weighted_gap({"calcium": 500.0}, plain) == pytest.approx(0.75)
    assert weighted_gap({"calcium": 500.0}, stressed) == pytest.approx(1.125)
    # An emphasis costs nothing once the goal is met.
    assert weighted_gap({"calcium": 1000.0}, stressed) == 0.0


def test_a_weight_leaves_a_ceiling_alone():
    heavy = {"sodium": replace(GOALS["sodium"], weight=9.0)}

    # 3,000 mg is 50% over the 2,000 mg ceiling, costed at CEILING_WEIGHT's 2.0.
    assert weighted_gap({"sodium": 3000.0}, heavy) == pytest.approx(1.0)


# Two lunches a close call apart: pesarattu carries the protein, ragi mudde the
# calcium. One portion each, so the only thing being chosen is the dish.
PESARATTU = candidate(
    "Pesarattu", {"lunch"}, energy=400, protein=20, calcium=60, grams=(100.0,)
)
RAGI_MUDDE = candidate(
    "Ragi mudde", {"lunch"}, energy=400, protein=5, calcium=340, grams=(100.0,)
)


def test_an_emphasis_tips_a_close_choice_toward_its_nutrient():
    lunch = {"lunch": (PESARATTU, RAGI_MUDDE)}
    stressed = {**GOALS, "calcium": replace(GOALS["calcium"], weight=1.5 * EMPHASIS_FACTOR)}

    # At the usual weights pesarattu's extra 15 g of protein is worth 0.50 and
    # ragi mudde's extra 280 mg of calcium 0.42, so pesarattu wins by 0.08. At
    # calcium's emphasised 2.25 the calcium is worth 0.63: ragi mudde, by 0.13.
    usual = plan_day(day(slots=lunch), rng())
    leaning = plan_day(day(slots=lunch, goals=stressed), rng())

    assert [item.dish_id for item in usual] == [PESARATTU.dish_id]
    assert [item.dish_id for item in leaning] == [RAGI_MUDDE.dish_id]
