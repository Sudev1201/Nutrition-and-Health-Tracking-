"""The planner's hard constraints, as pure functions.

Every rule here is one the spec calls a constraint rather than a preference: an
observance day, an avoided food, a medication window. A dish that fails one is
never scored, so the engine cannot trade it back in.
"""

import datetime
import uuid

from app.planner.rules import (
    Candidate,
    DayRules,
    FoodRef,
    Observance,
    Portion,
    candidates_for_slot,
    favourite_hits,
    is_avoided,
    is_mineral_heavy,
    minutes_after,
    sunday_index,
    vegetarian_reason,
    wait_until,
)

FRIDAY = datetime.date(2026, 8, 21)
SUNDAY = datetime.date(2026, 8, 16)

CURD_ID = uuid.uuid4()
RICE_ID = uuid.uuid4()


def candidate(
    name: str,
    slots: set[str],
    diet: str = "vegetarian",
    ingredients: tuple[tuple[uuid.UUID, str], ...] = (
        (RICE_ID, "Rice, raw, milled"),
    ),
    per_100g: dict[str, float] | None = None,
    default_grams: float = 200.0,
) -> Candidate:
    return Candidate(
        dish_id=uuid.uuid5(uuid.NAMESPACE_DNS, name),
        name=name,
        slots=frozenset(slots),
        diet=diet,
        ingredient_ids=frozenset(i for i, _ in ingredients),
        ingredient_names=tuple(n for _, n in ingredients),
        per_100g=per_100g or {"energy": 130.0, "protein": 3.0, "calcium": 10.0},
        portions=(Portion(default_grams, "cup", 1.0, "1 cup"),),
        default_grams=default_grams,
    )


IDLI = candidate("Idli", {"breakfast", "snack1", "snack2", "dinner"})
SAMBAR_RICE = candidate("Rice with sambar", {"lunch", "dinner"})
CURD_RICE = candidate(
    "Curd rice",
    {"lunch", "dinner"},
    ingredients=(
        (RICE_ID, "Rice, raw, milled"),
        (CURD_ID, "Curd, cow milk"),
    ),
    per_100g={"energy": 120.0, "protein": 4.0, "calcium": 65.0},
)
EGG_CURRY = candidate("Egg curry", {"lunch", "dinner"}, diet="eggetarian")
FISH_CURRY = candidate("Fish curry", {"lunch", "dinner"}, diet="fishetarian")
CHICKEN_CURRY = candidate("Chicken curry", {"lunch", "dinner"}, diet="nonveg")
POOL = [IDLI, SAMBAR_RICE, CURD_RICE, EGG_CURRY, FISH_CURRY, CHICKEN_CURRY]


def names(candidates) -> set[str]:
    return {c.name for c in candidates}


def rules(**overrides) -> DayRules:
    base = {"vegetarian": False, "profile_diet": "non-vegetarian"}
    return DayRules(**{**base, **overrides})


# --- observance days -----------------------------------------------------------


def test_the_weekday_index_counts_from_sunday():
    assert sunday_index(SUNDAY) == 0
    assert sunday_index(FRIDAY) == 5


def test_a_weekday_rule_names_the_day_when_it_has_no_label():
    friday_rule = Observance(kind="weekday", weekday=5)

    assert vegetarian_reason(FRIDAY, [friday_rule]) == "your Friday rule"
    assert vegetarian_reason(SUNDAY, [friday_rule]) is None


def test_a_labelled_rule_is_explained_by_its_label():
    purattasi = Observance(
        kind="date_range",
        label="Purattasi",
        start_date=datetime.date(2026, 9, 17),
        end_date=datetime.date(2026, 10, 17),
    )

    assert (
        vegetarian_reason(datetime.date(2026, 10, 17), [purattasi]) == "Purattasi"
    )
    assert vegetarian_reason(datetime.date(2026, 10, 18), [purattasi]) is None


def test_a_single_date_rule_matches_only_that_date():
    festival = Observance(
        kind="single_date", label="Vinayaka Chaturthi", start_date=FRIDAY
    )

    assert vegetarian_reason(FRIDAY, [festival]) == "Vinayaka Chaturthi"
    assert (
        vegetarian_reason(FRIDAY + datetime.timedelta(days=1), [festival]) is None
    )


# On an observance day egg counts as non-vegetarian and goes with meat and fish.
def test_a_vegetarian_day_excludes_egg_fish_and_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(vegetarian=True))

    assert names(allowed) == {"Rice with sambar", "Curd rice"}


# --- the standing diet -----------------------------------------------------------


def test_an_eggetarian_gets_egg_but_not_fish_or_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(profile_diet="eggetarian"))

    assert names(allowed) == {"Rice with sambar", "Curd rice", "Egg curry"}


def test_a_fishetarian_gets_fish_and_egg_but_not_meat():
    allowed = candidates_for_slot(POOL, "lunch", rules(profile_diet="fishetarian"))

    assert "Fish curry" in names(allowed)
    assert "Egg curry" in names(allowed)
    assert "Chicken curry" not in names(allowed)


def test_a_non_vegetarian_gets_everything_on_an_ordinary_day():
    allowed = candidates_for_slot(POOL, "lunch", rules())

    assert names(allowed) == {
        "Rice with sambar",
        "Curd rice",
        "Egg curry",
        "Fish curry",
        "Chicken curry",
    }


def test_a_dish_is_only_offered_in_its_own_slots():
    assert "Idli" not in names(candidates_for_slot(POOL, "lunch", rules()))
    assert "Idli" in names(candidates_for_slot(POOL, "breakfast", rules()))


# --- avoided and favourite foods -------------------------------------------------


def test_an_avoided_dish_is_blocked_by_id():
    assert is_avoided(CURD_RICE, [FoodRef("Curd rice", CURD_RICE.dish_id, "dish")])
    assert not is_avoided(
        SAMBAR_RICE, [FoodRef("Curd rice", CURD_RICE.dish_id, "dish")]
    )


def test_an_avoided_ingredient_blocks_every_dish_containing_it():
    avoided = [FoodRef("Curd", CURD_ID, "ingredient")]

    assert is_avoided(CURD_RICE, avoided)
    assert not is_avoided(SAMBAR_RICE, avoided)


def test_free_text_avoidance_matches_names_case_insensitively():
    assert is_avoided(CURD_RICE, [FoodRef("curd")])
    assert is_avoided(CURD_RICE, [FoodRef("CURD RICE")])
    assert not is_avoided(SAMBAR_RICE, [FoodRef("curd")])
    assert not is_avoided(SAMBAR_RICE, [FoodRef("   ")])


def test_favourites_are_reported_by_label():
    favourites = [FoodRef("Curd", CURD_ID, "ingredient"), FoodRef("idli")]

    assert favourite_hits(CURD_RICE, favourites) == ("Curd",)
    assert favourite_hits(IDLI, favourites) == ("idli",)
    assert favourite_hits(SAMBAR_RICE, favourites) == ()


# --- medication windows ----------------------------------------------------------


def test_minutes_after_a_dose_is_none_when_the_slot_comes_first():
    assert minutes_after(datetime.time(7, 0), datetime.time(8, 0)) == 60
    assert minutes_after(datetime.time(22, 0), datetime.time(20, 30)) is None


def test_the_sixty_minute_wait_is_reported_as_a_clock_time():
    assert wait_until(datetime.time(7, 30), datetime.time(7, 0)) == datetime.time(8, 0)
    assert wait_until(datetime.time(8, 0), datetime.time(7, 0)) is None
    assert wait_until(datetime.time(6, 0), datetime.time(7, 0)) is None


def test_a_dish_is_mineral_heavy_at_a_tenth_of_the_days_requirement():
    requirement = {"calcium": 1000.0}

    # 200 g of curd rice at 65 mg/100 g = 130 mg, over the 100 mg line.
    assert is_mineral_heavy(CURD_RICE, rules(requirement=requirement))
    # 200 g of sambar rice at 10 mg/100 g = 20 mg.
    assert not is_mineral_heavy(SAMBAR_RICE, rules(requirement=requirement))


def test_calcium_heavy_dishes_are_refused_inside_four_hours_of_the_dose():
    inside = rules(
        minutes_since_dose={"lunch": 180}, requirement={"calcium": 1000.0}
    )
    clear = rules(minutes_since_dose={"lunch": 300}, requirement={"calcium": 1000.0})
    before = rules(minutes_since_dose={"lunch": None}, requirement={"calcium": 1000.0})

    assert "Curd rice" not in names(candidates_for_slot(POOL, "lunch", inside))
    assert "Rice with sambar" in names(candidates_for_slot(POOL, "lunch", inside))
    assert "Curd rice" in names(candidates_for_slot(POOL, "lunch", clear))
    assert "Curd rice" in names(candidates_for_slot(POOL, "lunch", before))
