"""Postmenopausal status, and the iron target it selects.

ICMR-NIN 2020 publishes no postmenopausal category. Its 29 mg figure for women
already averages menstrual loss, so applying it to a woman who no longer
menstruates would substantially overstate her requirement -- and there is no
route of iron excretion. The spec falls back to the IOM value, 8 mg, with a
visible note that a different framework is being used.
"""

import datetime

import pytest

from app.models.food import Dish, DishIngredient, Ingredient, IngredientNutrient
from tests.test_tracking_api import PROFILE, nutrient

TODAY = datetime.date(2026, 8, 17)

WOMAN = {
    **PROFILE,
    "sex": "female",
    "age": 52,
    "weight_kg": 55.0,
    "menstrual_status": "menstruating",
}
POSTMENOPAUSAL = {**WOMAN, "menstrual_status": "postmenopausal"}


@pytest.fixture
def iron_rich_dish(db, iron_reference) -> Dish:
    """40 mg of iron in a 100 g portion: enough for one day to near the 45 mg limit."""
    ingredient = Ingredient(code="test:iron-rich", name="Iron-rich test food", source="IFCT")
    db.add(ingredient)
    db.flush()
    db.add(
        IngredientNutrient(
            ingredient_id=ingredient.id,
            nutrient_id=iron_reference.id,
            per_100g=40.0,
            source="IFCT",
        )
    )
    dish = Dish(
        code="test:iron-dish",
        name="Iron-rich dish",
        source="authored",
        is_editable=True,
        yield_factor=1.0,
    )
    db.add(dish)
    db.flush()
    db.add(DishIngredient(dish_id=dish.id, ingredient_id=ingredient.id, grams=100.0))
    db.flush()
    return dish


def targets(api) -> dict:
    response = api.get(f"/targets/today?date={TODAY}")
    assert response.status_code == 200, response.text
    return response.json()


def kinds(payload: dict) -> list[str]:
    return [w["kind"] for w in payload["warnings"]]


def test_the_status_reads_back(signed_in):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    assert signed_in.get("/profile").json()["menstrual_status"] == "postmenopausal"


def test_a_mans_profile_never_carries_a_status(signed_in):
    signed_in.put("/profile", json={**PROFILE, "menstrual_status": "menstruating"})
    assert signed_in.get("/profile").json()["menstrual_status"] is None


def test_an_unknown_status_is_refused(signed_in):
    response = signed_in.put("/profile", json={**WOMAN, "menstrual_status": "pregnant"})
    assert response.status_code == 422


def test_a_profile_saved_without_the_field_reads_as_unset(signed_in):
    signed_in.put("/profile", json={**PROFILE, "sex": "female", "weight_kg": 55.0})
    assert signed_in.get("/profile").json()["menstrual_status"] is None


def test_a_menstruating_woman_gets_the_icmr_figure(signed_in, iron_reference):
    signed_in.put("/profile", json=WOMAN)
    payload = targets(signed_in)

    assert nutrient(payload, "iron")["rda"] == 29
    assert "reference-framework" not in kinds(payload)


def test_a_postmenopausal_woman_gets_the_iom_figure(signed_in, iron_reference):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    assert nutrient(targets(signed_in), "iron")["rda"] == 8


def test_the_iom_figure_says_it_is_not_icmrs(signed_in, iron_reference):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    notes = [w for w in targets(signed_in)["warnings"] if w["kind"] == "reference-framework"]

    assert len(notes) == 1
    assert "IOM" in notes[0]["message"]
    assert "8 mg" in notes[0]["message"]


def test_only_iron_changes_band(signed_in, iron_reference):
    # The 60+ band carries four nutrients; switching her whole band would drop the rest.
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    payload = targets(signed_in)

    assert nutrient(payload, "calcium")["rda"] == 1000
    assert nutrient(payload, "thiamine")["rda"] == pytest.approx(1.4)


def test_a_woman_over_sixty_gets_the_note_too(signed_in, iron_reference):
    # Her band already gave her the IOM figure, silently. Now it says so.
    signed_in.put("/profile", json={**WOMAN, "age": 64, "menstrual_status": None})
    payload = targets(signed_in)

    assert nutrient(payload, "iron")["rda"] == 8
    assert "reference-framework" in kinds(payload)


def test_iron_near_the_limit_is_flagged_after_menopause(signed_in, iron_rich_dish):
    signed_in.put("/profile", json=POSTMENOPAUSAL)
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(iron_rich_dish.id),
            "food_kind": "dish", "grams": 100, "is_estimated": False,
        },
    )
    notes = [w for w in targets(signed_in)["warnings"] if w["kind"] == "approaching-limit"]

    assert len(notes) == 1
    assert "45 mg" in notes[0]["message"]


def test_the_same_day_is_not_flagged_before_menopause(signed_in, iron_rich_dish):
    signed_in.put("/profile", json=WOMAN)
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(iron_rich_dish.id),
            "food_kind": "dish", "grams": 100, "is_estimated": False,
        },
    )
    assert "approaching-limit" not in kinds(targets(signed_in))
