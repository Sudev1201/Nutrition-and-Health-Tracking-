"""End-to-end tests for the tracking loop: profile -> targets -> diary -> carry.

These build their own reference rows (see the `reference_data` fixture), so the
numbers they assert are the real ICMR-NIN ones without depending on the ETL.
"""

import datetime

import pytest

TODAY = datetime.date(2026, 8, 17)
YESTERDAY = TODAY - datetime.timedelta(days=1)

PROFILE = {
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
    "allergies": [],
    "favourites": [],
}


def nutrient(payload: dict, code: str) -> dict:
    return next(item for item in payload["nutrients"] if item["code"] == code)


def test_profile_is_absent_before_onboarding(signed_in):
    assert signed_in.get("/profile").status_code == 404


def test_targets_need_a_profile(signed_in, reference_data):
    assert signed_in.get(f"/targets/today?date={TODAY}").status_code == 404


def test_a_saved_profile_reads_back(signed_in):
    assert signed_in.put("/profile", json=PROFILE).status_code == 200

    saved = signed_in.get("/profile").json()
    assert saved["weight_kg"] == 65.0
    assert saved["activity"] == "sedentary"
    assert len(saved["meal_times"]) == 5


def test_saving_a_profile_twice_replaces_rather_than_duplicates(signed_in):
    signed_in.put("/profile", json=PROFILE)
    signed_in.put("/profile", json={**PROFILE, "weight_kg": 70.0})

    saved = signed_in.get("/profile").json()
    assert saved["weight_kg"] == 70.0
    assert len(saved["meal_times"]) == 5


"""
The reference man is 65 kg, sedentary, and ICMR publishes 2,110 kcal and 54.0 g
of protein for him. Those are the strongest available checks that the whole
chain -- profile, reference lookup, energy formula -- is wired up correctly.
"""


def test_targets_reproduce_the_icmr_reference_figures(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    payload = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert nutrient(payload, "energy")["rda"] == pytest.approx(2110, abs=12)
    assert nutrient(payload, "protein")["rda"] == pytest.approx(54.0, abs=0.1)


def test_micronutrient_targets_come_from_the_seeded_reference_tables(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["rda"] == 1000
    assert calcium["ear"] == 800
    assert calcium["tul"] == 2500


# ICMR deliberately set no upper limit for B12, and the app must not invent one.
def test_a_nutrient_with_no_published_limit_reports_none(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    b12 = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "vitamin_b12")

    assert b12["tul"] is None


def test_the_b_vitamin_column_matches_the_activity_level(signed_in, reference_data):
    """Using the headline (moderate) figures for a sedentary user over-targets
    thiamine, riboflavin, niacin and B6 by roughly 25%."""
    signed_in.put("/profile", json=PROFILE)
    sedentary = signed_in.get(f"/targets/today?date={TODAY}").json()

    signed_in.put("/profile", json={**PROFILE, "activity": "heavy"})
    heavy = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert nutrient(heavy, "thiamine")["rda"] > nutrient(sedentary, "thiamine")["rda"]


def test_hypertension_tightens_the_sodium_ceiling(signed_in, reference_data):
    signed_in.put("/profile", json={**PROFILE, "conditions": ["hypertension"]})

    sodium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "sodium")

    assert sodium["rda"] == 1500
    assert sodium["kind"] == "ceiling"


def test_conflicting_conditions_are_flagged_rather_than_averaged(signed_in, reference_data):
    signed_in.put(
        "/profile", json={**PROFILE, "conditions": ["hypertension", "hypotension"]}
    )

    payload = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert any(w["kind"] == "condition-conflict" for w in payload["warnings"])
    assert nutrient(payload, "sodium")["rda"] == 2000


def test_a_levothyroxine_dose_produces_a_timing_warning(signed_in, reference_data):
    signed_in.put(
        "/profile",
        json={
            **PROFILE,
            "conditions": ["hypothyroidism"],
            "medications": [{"name": "Levothyroxine", "time": "07:00"}],
        },
    )

    payload = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert any(w["kind"] == "medication-timing" for w in payload["warnings"])


# --- the diary ---------------------------------------------------------------


def test_an_empty_day_has_five_slots_and_nothing_logged(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    diary = signed_in.get(f"/diary?date={TODAY}").json()

    assert [slot["slot"] for slot in diary["slots"]] == [
        "breakfast", "snack1", "lunch", "snack2", "dinner",
    ]
    assert all(slot["state"] == "empty" for slot in diary["slots"])


def test_a_logged_meal_appears_in_the_diary(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    dish = reference_data

    created = signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY),
            "slot": "lunch",
            "food_id": str(dish.id),
            "food_kind": "dish",
            "grams": 200,
            "is_estimated": False,
        },
    )
    assert created.status_code == 201

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    lunch = next(slot for slot in diary["slots"] if slot["slot"] == "lunch")

    assert lunch["state"] == "logged"
    assert lunch["entries"][0]["name"] == dish.name
    # A weight given directly reads back as itself.
    assert lunch["entries"][0]["portion"] == "200 g"


def test_a_logged_meal_moves_the_day_totals(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    dish = reference_data

    before = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "energy")
    assert before["consumed"] == 0

    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": 200, "is_estimated": False,
        },
    )

    after = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "energy")
    assert after["consumed"] > 0


def test_an_entry_can_be_removed(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    dish = reference_data
    entry_id = signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": 200, "is_estimated": False,
        },
    ).json()["id"]

    assert signed_in.delete(f"/diary/entries/{entry_id}").status_code == 204

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    lunch = next(slot for slot in diary["slots"] if slot["slot"] == "lunch")
    assert lunch["state"] == "empty"


def test_an_estimated_entry_is_marked_as_such(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    dish = reference_data

    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY), "slot": "snack2", "food_id": str(dish.id),
            "food_kind": "dish", "grams": 150, "is_estimated": True,
        },
    )

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    snack = next(slot for slot in diary["slots"] if slot["slot"] == "snack2")
    assert snack["entries"][0]["is_estimated"] is True


# --- the compensation ledger, end to end -------------------------------------


def log_small_meal(api, dish, on_date):
    api.post(
        "/diary/entries",
        json={
            "date": str(on_date), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": 50, "is_estimated": False,
        },
    )


def test_a_shortfall_yesterday_raises_todays_calcium_target(signed_in, reference_data):
    """The central idea of the app: a compensable nutrient missed yesterday is
    made up over the next two days, within the cap."""
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, YESTERDAY)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["carried_in"] > 0
    assert calcium["target_effective"] > calcium["rda"]


"""
And the counterpart: protein has no storage pool, so a shortfall expires at
midnight. A future change that treats every nutrient the same breaks this.
"""


def test_a_protein_shortfall_yesterday_does_not_raise_todays_target(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, YESTERDAY)

    protein = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "protein")

    assert protein["carried_in"] == 0
    assert protein["target_effective"] == pytest.approx(protein["rda"])


def test_a_day_with_nothing_logged_creates_no_carry(signed_in, reference_data):
    """A day you did not use the app is untracked, not a day you ate nothing.
    Treating it as a total shortfall would flood every following day."""
    signed_in.put("/profile", json=PROFILE)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["carried_in"] == 0


def test_the_tracking_endpoints_require_sign_in(api_client):
    assert api_client.get("/profile").status_code == 401
    assert api_client.get(f"/targets/today?date={TODAY}").status_code == 401
    assert api_client.get(f"/diary?date={TODAY}").status_code == 401
