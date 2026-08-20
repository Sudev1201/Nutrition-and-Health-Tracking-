"""Household measures, and how they resolve to an absolute weight.

Every quantity in the app is two numbers: a household measure the user actually
thinks in ("half a bowl"), and the absolute weight the nutrient tables need.
"""

import pytest

from app.foods.measures import (
    GENERIC_MEASURES,
    format_quantity,
    normalise_measure_name,
    resolve_grams,
)


# INDB stores its serving unit as "1 cup" and "1 serving", so the count is baked
# into the name. Left alone, the picker would offer "2 × 1 cup".
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 cup", "cup"),
        ("1 serving", "serving"),
        ("cup", "cup"),
        ("tall glass", "tall glass"),
        ("  Bowl ", "bowl"),
    ],
)
def test_measure_names_are_normalised(raw, expected):
    assert normalise_measure_name(raw) == expected


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        (0.25, "¼"),
        (0.5, "½"),
        (0.75, "¾"),
        (1.0, "1"),
        (1.5, "1½"),
        (2.0, "2"),
        (2.5, "2½"),
        (3.0, "3"),
    ],
)
def test_quantities_read_the_way_people_say_them(quantity, expected):
    assert format_quantity(quantity) == expected


def test_a_whole_measure_resolves_to_its_full_weight():
    assert resolve_grams(quantity=1.0, measure_grams=180.0) == 180.0


def test_half_a_measure_is_half_the_weight():
    assert resolve_grams(quantity=0.5, measure_grams=180.0) == 90.0


def test_two_and_a_half_measures_scale_up():
    assert resolve_grams(quantity=2.5, measure_grams=180.0) == 450.0


"""
The generic set exists because no ingredient carries a measure of its own -- only
dishes do. A cup of raw rice and a cup of spinach differ several-fold, so these
are explicitly approximate rather than pretending to a precision we do not have.
"""


def test_generic_measures_are_all_marked_approximate():
    assert all(measure.is_approximate for measure in GENERIC_MEASURES)


def test_generic_measures_cover_the_common_vessels():
    names = {measure.name for measure in GENERIC_MEASURES}

    assert {"cup", "glass", "tablespoon", "teaspoon"} <= names


# A drinking vessel means the absolute reads in ml; everything else in grams.
def test_a_drinking_vessel_reports_its_absolute_in_millilitres():
    glass = next(measure for measure in GENERIC_MEASURES if measure.name == "glass")

    assert glass.unit == "ml"


def test_a_solid_measure_reports_its_absolute_in_grams():
    cup = next(measure for measure in GENERIC_MEASURES if measure.name == "tablespoon")

    assert cup.unit == "g"


# --- through the API ---------------------------------------------------------

import datetime

TODAY = datetime.date(2026, 8, 17)

PROFILE = {
    "sex": "male", "age": 25, "weight_kg": 65.0, "activity": "sedentary",
    "goal": "maintain", "pace": None, "diet_type": "vegetarian",
    "cereal_dominant": False, "conditions": [], "medications": [],
    "meal_times": [], "observances": [], "avoided": [], "favourites": [],
    "usual_intake": [],
}


def test_a_dish_offers_its_own_measure_first(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="1 cup", grams=185.0, is_default=True))
    db.flush()

    measures = signed_in.get(f"/foods/dish/{reference_data.id}/measures").json()["measures"]

    assert measures[0]["name"] == "cup"
    assert measures[0]["grams"] == 185.0
    assert measures[0]["is_approximate"] is False


def test_a_food_with_no_measure_of_its_own_still_offers_the_generic_set(
    signed_in, reference_data
):
    measures = signed_in.get(f"/foods/dish/{reference_data.id}/measures").json()["measures"]

    assert {m["name"] for m in measures} >= {"cup", "glass", "tablespoon"}
    assert all(m["is_approximate"] for m in measures)


def log(api, dish, **overrides):
    body = {
        "date": str(TODAY), "slot": "lunch", "food_id": str(dish.id),
        "food_kind": "dish", "is_estimated": False,
    }
    return api.post("/diary/entries", json={**body, **overrides})


"""
Half a bowl is the whole point of the request: the quantity and the measure are
chosen separately, and the absolute is derived from them.
"""


def test_half_a_measure_resolves_to_half_its_weight(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="bowl", grams=200.0))
    db.flush()
    signed_in.put("/profile", json=PROFILE)

    assert log(signed_in, reference_data, measure_name="bowl", quantity=0.5).status_code == 201

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["grams"] == 100.0


def test_the_diary_reads_the_portion_back_the_way_it_was_entered(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="bowl", grams=200.0))
    db.flush()
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, measure_name="bowl", quantity=0.5)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["portion"] == "½ bowl"


def test_a_whole_measure_reads_without_a_fraction(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="bowl", grams=200.0))
    db.flush()
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, measure_name="bowl", quantity=1)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["portion"] == "1 bowl"


def test_the_absolute_weight_comes_back_alongside_the_measure(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="bowl", grams=200.0))
    db.flush()
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, measure_name="bowl", quantity=1.5)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["grams"] == 300.0
    assert entry["measure_name"] == "bowl"
    assert entry["quantity"] == 1.5


"""
A generic measure's weight is a general figure, not one measured for this food.
Intake logged with one is estimated by definition, and the weekly report already
separates estimated from measured -- so the flag is set rather than trusted to
the user remembering to tick it.
"""


def test_a_generic_measure_marks_the_entry_estimated(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, measure_name="cup", quantity=1)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["is_estimated"] is True


def test_a_measure_seeded_for_this_food_is_not_estimated(signed_in, reference_data, db):
    from app.models.food import PortionMeasure

    db.add(PortionMeasure(dish_id=reference_data.id, measure_name="bowl", grams=200.0))
    db.flush()
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, measure_name="bowl", quantity=1)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["is_estimated"] is False


def test_an_absolute_weight_can_still_be_given_directly(signed_in, reference_data):
    """Someone with kitchen scales should not have to pick a vessel."""
    signed_in.put("/profile", json=PROFILE)

    log(signed_in, reference_data, grams=175)

    entry = signed_in.get(f"/diary?date={TODAY}").json()["slots"][2]["entries"][0]
    assert entry["grams"] == 175.0


def test_an_unknown_measure_is_refused_rather_than_silently_weighed(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    response = log(signed_in, reference_data, measure_name="thimble", quantity=1)

    assert response.status_code == 422


def test_an_entry_needs_either_a_measure_or_a_weight(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    assert log(signed_in, reference_data).status_code == 422
