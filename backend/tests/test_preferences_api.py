"""Food preferences, and the usual-intake baseline.

Onboarding never asks for a calorie figure — most people do not know theirs, and
a guess would be worse than nothing. It asks what a usual day looks like as real
foods instead, and the baseline is computed from the food database.
"""

import datetime

import pytest

TODAY = datetime.date(2026, 8, 17)

BASE_PROFILE = {
    "sex": "male",
    "age": 25,
    "weight_kg": 65.0,
    "activity": "sedentary",
    "goal": "maintain",
    "pace": None,
    "diet_type": "vegetarian",
    "cereal_dominant": False,
    "conditions": [],
    "medications": [],
    "meal_times": [
        {"slot": "breakfast", "time": "08:00", "weekend_time": None, "reminder_on": True},
        {"slot": "snack1", "time": "11:00", "weekend_time": None, "reminder_on": False},
        {"slot": "lunch", "time": "13:30", "weekend_time": None, "reminder_on": True},
        {"slot": "snack2", "time": "17:00", "weekend_time": None, "reminder_on": True},
        {"slot": "dinner", "time": "20:30", "weekend_time": None, "reminder_on": True},
    ],
    "observances": [],
    "avoided": [],
    "favourites": [],
    "usual_intake": [],
}


def profile_with(**overrides) -> dict:
    return {**BASE_PROFILE, **overrides}


# --- multiple favourites and multiple foods to avoid -------------------------


def test_several_favourites_are_all_kept(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json=profile_with(
            favourites=[
                {"label": "Curd", "food_id": None, "food_kind": None},
                {"label": "Milk", "food_id": None, "food_kind": None},
                {"label": "Apple", "food_id": None, "food_kind": None},
            ]
        ),
    )

    saved = signed_in.get("/profile").json()
    assert [item["label"] for item in saved["favourites"]] == ["Curd", "Milk", "Apple"]


def test_several_avoided_foods_are_all_kept(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json=profile_with(
            avoided=[
                {"label": "Peanut", "food_id": None, "food_kind": None},
                {"label": "Prawn", "food_id": None, "food_kind": None},
            ]
        ),
    )

    saved = signed_in.get("/profile").json()
    assert [item["label"] for item in saved["avoided"]] == ["Peanut", "Prawn"]


def test_the_two_lists_stay_separate(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json=profile_with(
            favourites=[{"label": "Curd", "food_id": None, "food_kind": None}],
            avoided=[{"label": "Peanut", "food_id": None, "food_kind": None}],
        ),
    )

    saved = signed_in.get("/profile").json()
    assert [item["label"] for item in saved["favourites"]] == ["Curd"]
    assert [item["label"] for item in saved["avoided"]] == ["Peanut"]


"""
A preference picked from search carries the food's id, which is what lets the
planner act on it later rather than string-matching a name against 547
ingredients.
"""


def test_a_preference_chosen_from_search_keeps_the_food_reference(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json=profile_with(
            favourites=[
                {
                    "label": reference_data.name,
                    "food_id": str(reference_data.id),
                    "food_kind": "dish",
                }
            ]
        ),
    )

    saved = signed_in.get("/profile").json()
    assert saved["favourites"][0]["food_id"] == str(reference_data.id)
    assert saved["favourites"][0]["food_kind"] == "dish"


def test_a_freely_typed_preference_is_still_allowed(signed_in, reference_data):
    """The UI only offers foods from the database, so nothing new arrives without
    an id. The API stays permissive anyway, because rows saved before that rule
    existed carry a null `food_id` and must survive a profile re-save — the
    wizard prefills them and sends them straight back."""
    signed_in.put(
        "/profile",
        json=profile_with(favourites=[{"label": "Amma's rasam", "food_id": None, "food_kind": None}]),
    )

    saved = signed_in.get("/profile").json()
    assert saved["favourites"][0]["label"] == "Amma's rasam"
    assert saved["favourites"][0]["food_id"] is None


def test_saving_again_replaces_the_lists_rather_than_appending(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json=profile_with(favourites=[{"label": "Curd", "food_id": None, "food_kind": None}]),
    )
    signed_in.put(
        "/profile",
        json=profile_with(favourites=[{"label": "Milk", "food_id": None, "food_kind": None}]),
    )

    saved = signed_in.get("/profile").json()
    assert [item["label"] for item in saved["favourites"]] == ["Milk"]


# --- observances survive a round trip ---------------------------------------
#
# `PUT /profile` replaces the whole questionnaire rather than merging, which is
# what makes an unticked condition genuinely go away. The cost of that choice is
# that anything the GET does not return is destroyed by the next save: a client
# reads the profile, edits one section, sends it back, and every field missing
# from the response is now gone. `observances` was exactly that hole.


WEDNESDAY = {
    "kind": "weekday",
    "weekday": 3,
    "start_date": None,
    "end_date": None,
    "label": "No meat on Wednesdays",
}

PURATTASI = {
    "kind": "date_range",
    "weekday": None,
    "start_date": "2026-09-18",
    "end_date": "2026-10-17",
    "label": "Purattasi",
}


def test_observances_are_returned_by_the_profile(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(observances=[WEDNESDAY]))

    saved = signed_in.get("/profile").json()
    assert saved["observances"] == [WEDNESDAY]


def test_all_three_observance_shapes_survive(signed_in, reference_data):
    """The model deliberately covers a weekday, a date range and a single date."""
    festival = {
        "kind": "single_date",
        "weekday": None,
        "start_date": "2026-11-08",
        "end_date": None,
        "label": "Karthigai Deepam",
    }
    signed_in.put(
        "/profile", json=profile_with(observances=[WEDNESDAY, PURATTASI, festival])
    )

    saved = signed_in.get("/profile").json()
    assert sorted(item["label"] for item in saved["observances"]) == [
        "Karthigai Deepam",
        "No meat on Wednesdays",
        "Purattasi",
    ]


def test_reading_a_profile_and_saving_it_back_keeps_the_observances(signed_in, reference_data):
    """The round trip a profile screen actually performs.

    This is the regression that matters: before `observances` was added to
    `ProfileOut`, this test wiped a saved vegetarian-day rule without any error,
    because the client could not send back a field it was never given.
    """
    signed_in.put("/profile", json=profile_with(observances=[WEDNESDAY, PURATTASI]))

    read_back = signed_in.get("/profile").json()
    signed_in.put("/profile", json={**read_back, "weight_kg": 66.0})

    saved = signed_in.get("/profile").json()
    assert sorted(item["label"] for item in saved["observances"]) == [
        "No meat on Wednesdays",
        "Purattasi",
    ]
    assert saved["weight_kg"] == 66.0


# --- the usual-intake baseline ----------------------------------------------


def usual_day(dish, grams_per_slot=200.0):
    return [
        {
            "slot": slot,
            "label": dish.name,
            "food_id": str(dish.id),
            "food_kind": "dish",
            "grams": grams_per_slot,
        }
        for slot in ("breakfast", "lunch", "dinner")
    ]


def test_a_usual_day_is_saved(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    saved = signed_in.get("/profile").json()
    assert len(saved["usual_intake"]) == 3
    assert saved["usual_intake"][0]["slot"] == "breakfast"


def test_the_baseline_needs_a_profile(signed_in):
    assert signed_in.get("/profile/baseline").status_code == 404


"""
The fixture dish is 150 kcal per 100 g, so three 200 g portions is 900 kcal.
This is the calculation the app was not doing.
"""


def test_the_baseline_adds_up_a_usual_day(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["usual_energy_kcal"] == pytest.approx(900, abs=1)


def test_the_baseline_reports_the_target_alongside_it(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["target_energy_kcal"] == pytest.approx(2110, abs=12)


def test_the_baseline_reports_the_gap(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["difference_kcal"] == pytest.approx(
        baseline["usual_energy_kcal"] - baseline["target_energy_kcal"], abs=0.5
    )


"""
The spec: if the computed intake and the computed requirement are wildly apart,
that is worth surfacing before generating a plan -- it usually means a mistyped
weight or a half-described day, not a real 1,200 kcal deficit.
"""


def test_an_implausible_gap_is_flagged(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["implausible"] is True
    assert baseline["note"] is not None


def test_a_reasonable_day_is_not_flagged(signed_in, reference_data):
    # ~2,100 kcal against a 2,110 kcal target.
    signed_in.put(
        "/profile", json=profile_with(usual_intake=usual_day(reference_data, grams_per_slot=467))
    )

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["implausible"] is False
    assert baseline["note"] is None


# --- the baseline covers every nutrient, not just energy ---------------------
#
# The fixture dish carries 150 kcal, 4 g protein and 30 mg calcium per 100 g, so
# a usual day of three 200 g portions is 600 g: 900 kcal, 24 g protein, 180 mg
# calcium, and no sodium at all.


def nutrient_named(baseline: dict, code: str) -> dict:
    return next(item for item in baseline["nutrients"] if item["code"] == code)


def test_the_baseline_reports_every_nutrient(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    baseline = signed_in.get("/profile/baseline").json()

    codes = {item["code"] for item in baseline["nutrients"]}
    assert {"energy", "protein", "calcium", "sodium"} <= codes


def test_the_baseline_adds_up_a_micronutrient(signed_in, reference_data):
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    calcium = nutrient_named(signed_in.get("/profile/baseline").json(), "calcium")

    assert calcium["usual"] == pytest.approx(180, abs=1)
    assert calcium["rda"] == pytest.approx(1000, abs=1)


def test_a_micronutrient_short_of_its_rda_is_flagged(signed_in, reference_data):
    """180 mg of calcium against a 1,000 mg target is the gap worth showing."""
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    calcium = nutrient_named(signed_in.get("/profile/baseline").json(), "calcium")

    assert calcium["off_target"] is True


def test_a_ceiling_nutrient_under_its_limit_is_not_flagged(signed_in, reference_data):
    """The asymmetry that a naive `usual - rda` would get backwards.

    Sodium is a ceiling, not a target. A usual day well under it is good news,
    and reporting it as a shortfall would tell the user to eat more salt.
    """
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    sodium = nutrient_named(signed_in.get("/profile/baseline").json(), "sodium")

    assert sodium["kind"] == "ceiling"
    assert sodium["usual"] == pytest.approx(0, abs=0.01)
    assert sodium["off_target"] is False


def test_a_baseline_nutrient_carries_its_unit_and_display_name(signed_in, reference_data):
    """Matching the `targets/today` convention: each row is self-describing."""
    signed_in.put("/profile", json=profile_with(usual_intake=usual_day(reference_data)))

    calcium = nutrient_named(signed_in.get("/profile/baseline").json(), "calcium")

    assert calcium["display_name"] == "Calcium"
    assert calcium["unit"] == "mg"
    assert calcium["category"] == "mineral"


def test_no_usual_day_means_no_nutrient_rows(signed_in, reference_data):
    """Empty, not zeroed -- the same reasoning as `usual_energy_kcal` being null."""
    signed_in.put("/profile", json=profile_with(usual_intake=[]))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["has_usual_intake"] is False
    assert baseline["nutrients"] == []


def test_no_usual_day_means_no_baseline_rather_than_zero(signed_in, reference_data):
    """Zero would read as "you eat nothing", which is a very different claim from
    "you have not told us yet"."""
    signed_in.put("/profile", json=profile_with(usual_intake=[]))

    baseline = signed_in.get("/profile/baseline").json()

    assert baseline["has_usual_intake"] is False
    assert baseline["usual_energy_kcal"] is None


# --- costing a day before it is saved ---------------------------------------


"""
The wizard shows a running total as foods are added, before there is a profile
to attach them to, so the totals have to be computable from the items alone.
"""


def test_nutrient_totals_can_be_costed_for_a_list_of_foods(signed_in, reference_data):
    response = signed_in.post(
        "/foods/nutrients",
        json={"items": [{"food_id": str(reference_data.id), "food_kind": "dish", "grams": 200}]},
    )

    assert response.status_code == 200
    assert response.json()["totals"]["energy"] == pytest.approx(300, abs=1)


def test_costing_sums_across_several_foods(signed_in, reference_data):
    response = signed_in.post(
        "/foods/nutrients",
        json={
            "items": [
                {"food_id": str(reference_data.id), "food_kind": "dish", "grams": 100},
                {"food_id": str(reference_data.id), "food_kind": "dish", "grams": 100},
            ]
        },
    )

    assert response.json()["totals"]["energy"] == pytest.approx(300, abs=1)


def test_costing_an_empty_list_is_zero_rather_than_an_error(signed_in, reference_data):
    response = signed_in.post("/foods/nutrients", json={"items": []})

    assert response.status_code == 200
    assert response.json()["totals"] == {}


def test_costing_requires_sign_in(api_client, reference_data):
    assert api_client.post("/foods/nutrients", json={"items": []}).status_code == 401
