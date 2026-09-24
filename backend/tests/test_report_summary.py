"""The weekly report's arithmetic, on plain data.

What counts as met, which shortfalls were never made up and why, and what to suggest
for next week. No database: `app.reports.service` feeds these functions, and the
numbers here are chosen so each test has one obvious answer. Calcium is 1,000 mg a
day with an 800 mg EAR and a 2,500 mg upper limit, as ICMR-NIN 2020 has it.
"""

import datetime
import uuid

import pytest

from app.planner.rules import Candidate, FoodRef, Portion
from app.reports.summary import (
    DayFacts,
    Gap,
    NutrientMeta,
    NutrientWeek,
    foods_for,
    is_met,
    nutrients_to_suggest,
    suggestion_text,
    summarise,
    uncompensated,
)

SUNDAY = datetime.date(2026, 9, 13)


def meta(
    code: str,
    display_name: str,
    unit: str,
    category: str,
    kind: str = "target",
    *,
    compensable: bool = True,
    cap: float = 0.30,
) -> NutrientMeta:
    return NutrientMeta(
        code=code,
        display_name=display_name,
        unit=unit,
        category=category,
        kind=kind,
        is_compensable=compensable,
        carry_cap_fraction=cap,
    )


META = {
    m.code: m
    for m in (
        meta("energy", "Energy", "kcal", "macro"),
        meta("protein", "Protein", "g", "macro", compensable=False),
        meta("fibre", "Dietary fibre", "g", "macro", cap=0.25),
        meta("calcium", "Calcium", "mg", "mineral"),
        meta("sodium", "Sodium", "mg", "mineral", "ceiling", compensable=False),
        meta("vitamin_k", "Vitamin K", "ug", "vitamin"),
    )
}

BASE = {
    "energy": 2000.0,
    "protein": 54.0,
    "fibre": 30.0,
    "calcium": 1000.0,
    "sodium": 2000.0,
    "vitamin_k": 55.0,
}
EAR = {"protein": 43.0, "calcium": 800.0}
TUL = {"calcium": 2500.0}


def day(
    n: int,
    consumed: dict[str, float],
    *,
    coverage: dict[str, float] | None = None,
    effective: dict[str, float] | None = None,
    expired: dict[str, float] | None = None,
) -> DayFacts:
    """Day n of the week (0 = Sunday). Every code consumed is fully measured unless
    `coverage` says otherwise, and the effective targets are the base ones unless a
    carry moved them."""
    return DayFacts(
        date=SUNDAY + datetime.timedelta(days=n),
        consumed=consumed,
        coverage=coverage if coverage is not None else dict.fromkeys(consumed, 1.0),
        base=dict(BASE),
        ear={code: EAR.get(code) for code in BASE},
        effective={**BASE, **(effective or {})},
        tul={code: TUL.get(code) for code in BASE},
        expired_shortfall=expired or {},
    )


def row(weeks: list[NutrientWeek], code: str) -> NutrientWeek:
    return next(week for week in weeks if week.code == code)


# --- what counts as met ------------------------------------------------------------------------


def test_a_target_nutrient_is_met_from_its_ear():
    # 850 mg is short of the 1,000 mg target but clear of the 800 mg adequacy floor.
    assert is_met("target", 850.0, 800.0, 1000.0, 2500.0)


def test_under_the_ear_is_a_miss():
    assert not is_met("target", 790.0, 800.0, 1000.0, 2500.0)


def test_without_an_ear_the_effective_target_is_the_floor():
    # Fibre carrying 6 g in from a short day: 32 g no longer reaches it.
    assert not is_met("target", 32.0, None, 36.0, None)
    assert is_met("target", 36.0, None, 36.0, None)


def test_going_over_the_target_is_not_a_miss():
    assert is_met("target", 1800.0, 800.0, 1000.0, 2500.0)


def test_reaching_the_upper_limit_is_a_miss():
    # Reaching a limit exactly is already "above the limit" on Today
    # (status.ts: consumed >= limit).
    assert is_met("target", 2499.0, 800.0, 1000.0, 2500.0)
    assert not is_met("target", 2500.0, 800.0, 1000.0, 2500.0)
    assert not is_met("target", 2600.0, 800.0, 1000.0, 2500.0)


def test_a_low_sodium_day_is_not_a_miss():
    assert is_met("ceiling", 300.0, None, 2000.0, None)
    assert is_met("ceiling", 1999.0, None, 2000.0, None)
    assert not is_met("ceiling", 2000.0, None, 2000.0, None)
    assert not is_met("ceiling", 2001.0, None, 2000.0, None)


def test_a_ceiling_lowered_by_yesterdays_surplus_is_the_one_judged():
    # After a 4,000 mg day the next two ceilings drop to 1,400 mg (spec manual step 5).
    assert not is_met("ceiling", 1600.0, None, 1400.0, None)


# --- the week, per nutrient --------------------------------------------------------------------

# Calcium is met on Sunday, missed on Monday and over the limit on Tuesday, with the
# ledger's carries raising Monday's and Tuesday's targets. On Wednesday nothing logged
# had a calcium figure.
CALCIUM_WEEK = [
    day(0, {"energy": 1900.0, "calcium": 900.0}),
    day(
        1,
        {"energy": 1700.0, "calcium": 700.0},
        coverage={"energy": 1.0, "calcium": 0.5},
        effective={"calcium": 1050.0},
    ),
    day(
        2,
        {"energy": 2100.0, "calcium": 2600.0},
        coverage={"energy": 1.0, "calcium": 0.9},
        effective={"calcium": 1225.0},
    ),
    day(3, {"energy": 150.0}),
]


def test_only_measured_days_count():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert calcium.measured_days == 3
    assert calcium.consumed_total == pytest.approx(4200.0)


def test_the_target_total_sums_base_targets_not_effective_ones():
    # Monday's extra 50 mg is half of Sunday's 100 mg shortfall being made up:
    # summing effective targets would count that shortfall twice.
    assert row(summarise(CALCIUM_WEEK, META), "calcium").target_total == pytest.approx(3000.0)


def test_the_ear_total_sums_the_ear_over_measured_days():
    weeks = summarise(CALCIUM_WEEK, META)

    assert row(weeks, "calcium").ear_total == pytest.approx(2400.0)
    assert row(weeks, "energy").ear_total is None


def test_days_met_and_days_over_the_limit_are_counted_apart():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert calcium.days_met == 1
    assert calcium.days_over_limit == 1


def test_coverage_is_the_mean_over_measured_days():
    assert row(summarise(CALCIUM_WEEK, META), "calcium").coverage == pytest.approx(0.8)


def test_a_nutrient_nothing_measured_is_left_out():
    codes = [week.code for week in summarise(CALCIUM_WEEK, META)]
    assert "vitamin_k" not in codes
    assert "protein" not in codes


def test_the_row_carries_the_nutrients_own_names():
    calcium = row(summarise(CALCIUM_WEEK, META), "calcium")

    assert (calcium.display_name, calcium.unit, calcium.category, calcium.kind) == (
        "Calcium",
        "mg",
        "mineral",
        "target",
    )


def test_a_ceiling_counts_days_under_it():
    days = [
        day(0, {"sodium": 4000.0}),
        day(1, {"sodium": 1600.0}, effective={"sodium": 1400.0}),
        day(2, {"sodium": 1300.0}, effective={"sodium": 1400.0}),
    ]
    sodium = row(summarise(days, META), "sodium")

    assert sodium.days_met == 1
    assert sodium.target_total == pytest.approx(6000.0)


def test_nutrients_read_macros_then_minerals_then_vitamins():
    everything = dict.fromkeys(BASE, 1.0)
    codes = [week.code for week in summarise([day(0, everything)], META)]

    assert codes == ["fibre", "energy", "protein", "calcium", "sodium", "vitamin_k"]


def test_a_code_without_a_target_that_day_is_not_measured_against_one():
    cholesterol = meta("cholesterol", "Cholesterol", "mg", "macro", "ceiling")
    days = [day(0, {"cholesterol": 300.0})]

    assert summarise(days, {"cholesterol": cholesterol}) == []


def test_no_days_give_no_rows():
    assert summarise([], META) == []


# --- what was never made up --------------------------------------------------------------------


def test_a_shortfall_beyond_the_cap_is_uncompensated():
    # 100 mg on Sunday is 900 short; the next two days can take 300 each, so 300
    # expires. Monday, raised to 1,300, falls 900 short again and 300 more expires.
    days = [
        day(0, {"calcium": 100.0}, expired={"calcium": 300.0}),
        day(1, {"calcium": 400.0}, effective={"calcium": 1300.0}, expired={"calcium": 300.0}),
    ]

    assert uncompensated(days, META, frozenset()) == [
        Gap(
            code="calcium",
            display_name="Calcium",
            unit="mg",
            amount=600.0,
            reason_code="cap",
            reason="Beyond the 30% a day can carry, so it expired.",
        )
    ]


def test_fibre_names_its_own_tighter_cap():
    # 10 g of 30 is 20 short; 7.5 g a day for two days carries 15, and 5 expires.
    [gap] = uncompensated([day(0, {"fibre": 10.0}, expired={"fibre": 5.0})], META, frozenset())

    assert gap.amount == pytest.approx(5.0)
    assert gap.reason == "Beyond the 25% a day can carry, so it expired."


def test_a_protein_shortfall_is_never_carried():
    # 30 g of a 54 g target: all 24 g short expire on the day.
    [gap] = uncompensated([day(0, {"protein": 30.0}, expired={"protein": 24.0})], META, frozenset())

    assert gap.reason_code == "not_compensable"
    assert gap.reason == "Protein has no storage pool, so a short day is not carried forward."
    assert gap.amount == pytest.approx(24.0)


def test_another_nutrient_without_a_store_gets_the_general_reason():
    zinc = meta("zinc", "Zinc", "mg", "mineral", compensable=False)
    facts = DayFacts(
        date=SUNDAY,
        consumed={"zinc": 5.0},
        coverage={"zinc": 1.0},
        base={"zinc": 17.0},
        ear={"zinc": 14.0},
        effective={"zinc": 17.0},
        tul={"zinc": 40.0},
        expired_shortfall={"zinc": 12.0},
    )

    [gap] = uncompensated([facts], {"zinc": zinc}, frozenset())

    assert gap.reason == "Zinc is not carried forward: the body has no store of it to draw on."


def test_energy_is_never_reported_as_not_made_up():
    days = [day(0, {"energy": 200.0}, expired={"energy": 600.0})]
    assert uncompensated(days, META, frozenset()) == []


def test_a_nutrient_held_steady_is_never_reported():
    # On warfarin vitamin K is not averaged, so its whole shortfall "expires" by design.
    days = [day(0, {"vitamin_k": 20.0}, expired={"vitamin_k": 35.0})]

    assert uncompensated(days, META, frozenset({"vitamin_k"})) == []
    assert [gap.code for gap in uncompensated(days, META, frozenset())] == ["vitamin_k"]


def test_a_low_sodium_day_is_not_a_gap():
    # The ledger does record it as expired: sodium never carries a shortfall.
    days = [day(0, {"sodium": 500.0}, expired={"sodium": 1500.0})]
    assert uncompensated(days, META, frozenset()) == []


@pytest.mark.parametrize(("expired", "reported"), [(19.9, False), (20.0, True)])
def test_an_expiry_under_one_percent_of_the_week_is_left_out(expired, reported):
    # Two measured days of calcium: 2,000 mg of target, so the line is 20 mg. Sunday
    # falls 600 mg short plus the expiry: the carries take 600, and the rest expires.
    days = [
        day(0, {"calcium": 400.0 - expired}, expired={"calcium": expired}),
        day(1, {"calcium": 1300.0}, effective={"calcium": 1300.0}),
    ]
    assert bool(uncompensated(days, META, frozenset())) is reported


def test_gaps_follow_the_reports_order():
    days = [
        day(
            0,
            {"calcium": 100.0, "protein": 30.0},
            expired={"calcium": 300.0, "protein": 24.0},
        )
    ]
    assert [gap.code for gap in uncompensated(days, META, frozenset())] == ["protein", "calcium"]


# --- what to suggest ---------------------------------------------------------------------------


def week(
    code: str = "calcium",
    *,
    display_name: str | None = None,
    kind: str = "target",
    measured_days: int = 7,
    target_total: float = 7000.0,
    consumed_total: float = 4200.0,
    coverage: float = 0.9,
) -> NutrientWeek:
    return NutrientWeek(
        code=code,
        display_name=display_name or code.replace("_", " ").capitalize(),
        unit="mg",
        category="mineral",
        kind=kind,
        measured_days=measured_days,
        target_total=target_total,
        ear_total=None,
        consumed_total=consumed_total,
        days_met=0,
        days_over_limit=0,
        coverage=coverage,
    )


def suggested(
    weeks: list[NutrientWeek], tracked_days: int = 7, excluded: frozenset[str] = frozenset()
) -> list[str]:
    return [w.code for w in nutrients_to_suggest(weeks, tracked_days, excluded)]


def test_a_week_well_short_is_suggested():
    assert suggested([week(consumed_total=4200.0)]) == ["calcium"]


@pytest.mark.parametrize(("consumed", "codes"), [(6299.0, ["calcium"]), (6300.0, [])])
def test_ninety_percent_of_the_week_is_enough(consumed, codes):
    assert suggested([week(consumed_total=consumed)]) == codes


def test_the_worst_ratio_comes_first_and_three_at_most():
    weeks = [
        week("calcium", consumed_total=4200.0),  # 60%
        week("iron", consumed_total=2800.0),  # 40%
        week("fibre", consumed_total=5600.0),  # 80%
        week("vitamin_b12", consumed_total=3500.0),  # 50%
    ]
    assert suggested(weeks) == ["iron", "vitamin_b12", "calcium"]


@pytest.mark.parametrize(("measured", "codes"), [(3, []), (4, ["calcium"])])
def test_it_must_be_measured_on_half_the_tracked_days(measured, codes):
    assert suggested([week(measured_days=measured)], tracked_days=7) == codes


@pytest.mark.parametrize(("measured", "codes"), [(2, []), (3, ["calcium"])])
def test_it_must_be_measured_on_three_days_at_least(measured, codes):
    # Half of four tracked days is two, but two days say too little.
    assert suggested([week(measured_days=measured)], tracked_days=4) == codes


@pytest.mark.parametrize(("coverage", "codes"), [(0.49, []), (0.5, ["calcium"])])
def test_a_thinly_measured_nutrient_is_not_suggested(coverage, codes):
    assert suggested([week(coverage=coverage)]) == codes


def test_energy_and_ceilings_are_never_suggested():
    weeks = [week("energy", consumed_total=1000.0), week("sodium", kind="ceiling")]
    assert suggested(weeks) == []


def test_the_callers_exclusions_are_never_suggested():
    # Potassium on a potassium-sparing drug (spec manual step 7b).
    weeks = [week("potassium", consumed_total=1000.0), week("calcium")]
    assert suggested(weeks, excluded=frozenset({"potassium"})) == ["calcium"]


# --- which dishes ------------------------------------------------------------------------------


def dish(
    name: str,
    per_100g: dict[str, float],
    *,
    diet: str = "vegetarian",
    grams: float = 200.0,
    ingredients: tuple[str, ...] = (),
    dish_id: uuid.UUID | None = None,
) -> Candidate:
    return Candidate(
        dish_id=dish_id or uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset({"lunch", "dinner"}),
        diet=diet,
        ingredient_ids=frozenset(uuid.uuid5(uuid.NAMESPACE_DNS, i) for i in ingredients),
        ingredient_names=ingredients,
        per_100g=per_100g,
        portions=(Portion(grams, "cup", 1.0, "1 cup"),),
        default_grams=grams,
    )


# Calcium per default portion: paneer 400 mg, fish 330, ragi 300, curd rice 162.5,
# payasam 120, egg curry 100, idli none at all. B12: egg curry 1.2 ug, curd rice 0.5.
PANEER = dish(
    "Paneer butter masala", {"calcium": 200.0}, ingredients=("Paneer", "Butter", "Tomato")
)
FISH_FRY = dish("Fish fry", {"calcium": 220.0}, diet="fishetarian", grams=150.0)
RAGI_MUDDE = dish("Ragi mudde", {"calcium": 120.0}, grams=250.0)
CURD_RICE = dish("Curd rice", {"calcium": 65.0, "vitamin_b12": 0.2}, grams=250.0)
PAYASAM = dish("Moong dal payasam", {"calcium": 60.0})
EGG_CURRY = dish("Egg curry", {"calcium": 50.0, "vitamin_b12": 0.6}, diet="eggetarian")
IDLI = dish("Idli", {"energy": 130.0})
POOL = [IDLI, EGG_CURRY, PAYASAM, CURD_RICE, RAGI_MUDDE, FISH_FRY, PANEER]

NO_PANEER = (FoodRef(label="paneer"),)


def dish_names(candidates: list[Candidate]) -> list[str]:
    return [c.name for c in candidates]


def test_dishes_are_ranked_by_the_nutrient_in_a_default_portion():
    assert dish_names(foods_for("calcium", POOL, "vegetarian", ())) == [
        "Paneer butter masala",
        "Ragi mudde",
        "Curd rice",
    ]


def test_an_avoided_ingredient_is_never_suggested():
    assert dish_names(foods_for("calcium", POOL, "vegetarian", NO_PANEER)) == [
        "Ragi mudde",
        "Curd rice",
        "Moong dal payasam",
    ]


def test_an_avoided_dish_picked_from_search_is_never_suggested():
    avoided = (FoodRef(label="Ragi mudde", food_id=RAGI_MUDDE.dish_id, food_kind="dish"),)
    assert dish_names(foods_for("calcium", POOL, "vegetarian", avoided)) == [
        "Paneer butter masala",
        "Curd rice",
        "Moong dal payasam",
    ]


def test_the_diet_decides_what_may_be_suggested():
    assert dish_names(foods_for("calcium", POOL, "fishetarian", NO_PANEER)) == [
        "Fish fry",
        "Ragi mudde",
        "Curd rice",
    ]
    assert dish_names(foods_for("vitamin_b12", POOL, "vegetarian", ())) == ["Curd rice"]


def test_a_dish_without_the_nutrient_is_not_suggested():
    # Only two dishes carry any B12, so an eggetarian is offered two, not three.
    assert dish_names(foods_for("vitamin_b12", POOL, "eggetarian", ())) == [
        "Egg curry",
        "Curd rice",
    ]


def test_equal_dishes_go_by_name_whatever_their_case():
    # A dish the user typed in keeps the case they typed it in.
    pool = [dish("Beetroot poriyal", {"calcium": 50.0}), dish("avial", {"calcium": 50.0})]
    assert dish_names(foods_for("calcium", pool, "vegetarian", ())) == [
        "avial",
        "Beetroot poriyal",
    ]


def test_a_household_copy_of_a_dish_is_not_named_twice():
    copy = dish("Curd Rice", {"calcium": 70.0}, grams=250.0, dish_id=uuid.uuid4())
    chosen = foods_for("calcium", [*POOL, copy], "vegetarian", NO_PANEER)

    assert dish_names(chosen) == ["Ragi mudde", "Curd Rice", "Moong dal payasam"]
    assert chosen[1].dish_id == copy.dish_id


# --- the sentence ------------------------------------------------------------------------------


def test_the_suggestion_names_its_dishes():
    text = suggestion_text(week(display_name="Calcium"), [RAGI_MUDDE, CURD_RICE, PAYASAM])
    assert text == (
        "Calcium fell short this week. "
        "Dishes that carry it: Ragi mudde, Curd rice, Moong dal payasam."
    )


def test_two_dishes_are_listed_with_a_comma_in_the_order_given():
    text = suggestion_text(week(display_name="Calcium"), [CURD_RICE, RAGI_MUDDE])
    assert text == "Calcium fell short this week. Dishes that carry it: Curd rice, Ragi mudde."


def test_one_dish_stands_alone():
    text = suggestion_text(week("vitamin_b12", display_name="Vitamin B12"), [CURD_RICE])
    assert text == "Vitamin B12 fell short this week. Dishes that carry it: Curd rice."


def test_with_no_dishes_the_shortfall_is_still_said():
    assert suggestion_text(week(display_name="Calcium"), []) == "Calcium fell short this week."


def test_dish_names_keep_their_own_capitals():
    mysore = dish("Mysore masala dosa", {"calcium": 10.0})
    text = suggestion_text(week(display_name="Calcium"), [RAGI_MUDDE, mysore])
    assert text == "Calcium fell short this week. Dishes that carry it: Ragi mudde, Mysore masala dosa."
