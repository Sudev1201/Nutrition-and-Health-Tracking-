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


# --- skipping a meal on one day ----------------------------------------------
#
# `skipped` is not `empty`. Empty means the app does not know what happened;
# skipped means the user said nothing was eaten -- no time, or a fast. The
# frontend has rendered a third state from the start and could never receive one.


def skip(client, slot, date=TODAY):
    return client.post("/diary/skips", json={"date": str(date), "slot": slot})


def slot_named(diary: dict, slot: str) -> dict:
    return next(item for item in diary["slots"] if item["slot"] == slot)


def test_a_skipped_slot_reads_as_skipped_not_empty(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    assert skip(signed_in, "snack1").status_code == 201

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert slot_named(diary, "snack1")["state"] == "skipped"
    assert slot_named(diary, "lunch")["state"] == "empty"


def test_any_slot_can_be_skipped(signed_in, reference_data):
    """Not just the optional snacks. Someone fasting skips lunch and dinner too."""
    signed_in.put("/profile", json=PROFILE)

    for slot in ("breakfast", "lunch", "dinner"):
        assert skip(signed_in, slot).status_code == 201

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert [slot_named(diary, s)["state"] for s in ("breakfast", "lunch", "dinner")] == [
        "skipped", "skipped", "skipped",
    ]


def test_skipping_the_same_slot_twice_is_not_an_error(signed_in, reference_data):
    """A double tap on Skip should be idempotent, not a duplicate row or a 500."""
    signed_in.put("/profile", json=PROFILE)

    skip(signed_in, "snack1")
    assert skip(signed_in, "snack1").status_code in (200, 201)

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert slot_named(diary, "snack1")["state"] == "skipped"


def test_a_skip_can_be_undone(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    skip(signed_in, "snack1")

    undone = signed_in.request(
        "DELETE", "/diary/skips", json={"date": str(TODAY), "slot": "snack1"}
    )
    assert undone.status_code == 204

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert slot_named(diary, "snack1")["state"] == "empty"


def test_a_skip_belongs_to_one_day_only(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    skip(signed_in, "snack1", date=YESTERDAY)

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert slot_named(diary, "snack1")["state"] == "empty"


def test_logging_into_a_skipped_slot_makes_it_logged(signed_in, reference_data):
    """Food wins. Having eaten is a stronger fact than having said you would not."""
    signed_in.put("/profile", json=PROFILE)
    skip(signed_in, "lunch")

    signed_in.post(
        "/diary/entries",
        json={
            "date": str(TODAY),
            "slot": "lunch",
            "food_id": str(reference_data.id),
            "food_kind": "dish",
            "grams": 200,
            "is_estimated": False,
        },
    )

    diary = signed_in.get(f"/diary?date={TODAY}").json()
    assert slot_named(diary, "lunch")["state"] == "logged"


def test_an_unknown_slot_cannot_be_skipped(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    assert skip(signed_in, "brunch").status_code == 422


def test_a_day_of_only_skips_still_creates_no_carry(signed_in, reference_data):
    """A fast is not a debt to repay.

    Skips live outside `meal_logs` precisely so the day totals stay empty, which
    is what the targets service reads as "untracked". Generating a full day's
    shortfall here would push someone to overeat for the two days after a fast.
    """
    signed_in.put("/profile", json=PROFILE)
    for slot in ("breakfast", "snack1", "lunch", "snack2", "dinner"):
        skip(signed_in, slot, date=YESTERDAY)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["carried_in"] == 0


def test_skipping_requires_sign_in(api_client):
    assert api_client.post(
        "/diary/skips", json={"date": str(TODAY), "slot": "snack1"}
    ).status_code == 401


# --- four meals a day rather than five ---------------------------------------
#
# A standing preference about the shape of a normal day, which is a different
# statement from skipping a meal on one particular date.


def meal_times_with(**disabled) -> list[dict]:
    return [
        {**item, "is_enabled": not disabled.get(item["slot"], False)}
        for item in PROFILE["meal_times"]
    ]


def test_meal_slots_are_all_enabled_by_default(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    saved = signed_in.get("/profile").json()
    assert all(item["is_enabled"] for item in saved["meal_times"])


def test_a_disabled_snack_is_left_out_of_the_diary(signed_in, reference_data):
    signed_in.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})

    diary = signed_in.get(f"/diary?date={TODAY}").json()

    assert [slot["slot"] for slot in diary["slots"]] == [
        "breakfast", "lunch", "snack2", "dinner",
    ]


def test_disabling_a_snack_does_not_hide_a_past_day_that_used_it(signed_in, reference_data):
    """Turning a snack off changes the shape of a normal day from now on. It is
    not a claim about what was eaten last week, and hiding a real entry would be
    rewriting history."""
    signed_in.put("/profile", json=PROFILE)
    signed_in.post(
        "/diary/entries",
        json={
            "date": str(YESTERDAY),
            "slot": "snack1",
            "food_id": str(reference_data.id),
            "food_kind": "dish",
            "grams": 200,
            "is_estimated": False,
        },
    )

    signed_in.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})

    yesterday = signed_in.get(f"/diary?date={YESTERDAY}").json()
    assert slot_named(yesterday, "snack1")["state"] == "logged"

    today = signed_in.get(f"/diary?date={TODAY}").json()
    assert "snack1" not in [slot["slot"] for slot in today["slots"]]


def test_a_main_meal_cannot_be_disabled(signed_in, reference_data):
    """Four or five meals means one or two snacks. A day without lunch is a
    skipped lunch, not a meal-count preference -- and letting a main meal be
    switched off would make an unlogged one impossible to notice."""
    response = signed_in.put(
        "/profile", json={**PROFILE, "meal_times": meal_times_with(lunch=True)}
    )

    assert response.status_code == 422


def test_a_disabled_snack_survives_a_profile_round_trip(signed_in, reference_data):
    signed_in.put("/profile", json={**PROFILE, "meal_times": meal_times_with(snack1=True)})

    read_back = signed_in.get("/profile").json()
    signed_in.put("/profile", json={**read_back, "weight_kg": 66.0})

    saved = signed_in.get("/profile").json()
    snack1 = next(item for item in saved["meal_times"] if item["slot"] == "snack1")
    assert snack1["is_enabled"] is False


# --- an unmeasured nutrient is unknown, not zero -----------------------------
#
# A nutrient with no row on any of a day's foods contributed nothing to the
# totals, and `consumed.get(code, 0.0)` then turned that silence into a confident
# zero. The zero read as a full shortfall, and for a compensable nutrient the
# shortfall was carried forward two days -- so a coverage gap in the food tables
# manufactured a deficit the user never had.
#
# The fixture dish carries energy, protein and calcium only. Every other seeded
# nutrient -- potassium, B12, thiamine, fibre -- has no row on it at all.


def test_a_measured_nutrient_reports_full_coverage(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, TODAY)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["coverage"] == pytest.approx(1.0)


def test_a_nutrient_no_food_carries_reports_no_coverage(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, TODAY)

    potassium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "potassium")

    assert potassium["coverage"] == pytest.approx(0.0)


def test_a_day_with_nothing_logged_reports_no_coverage(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["coverage"] == pytest.approx(0.0)


def test_an_unmeasured_nutrient_carries_nothing_forward(signed_in, reference_data):
    """The bug this pins: 100 g of the fixture dish has no potassium row, so a
    full 3,510 mg shortfall used to be carried into today off the back of a
    number that was never measured."""
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, YESTERDAY)

    potassium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "potassium")

    assert potassium["carried_in"] == 0


def test_a_measured_shortfall_is_still_carried_forward(signed_in, reference_data):
    """The other half of it: calcium really was measured and really was short, so
    the ledger must still move. Silencing every carry would be the opposite bug."""
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, YESTERDAY)

    calcium = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "calcium")

    assert calcium["carried_in"] > 0


def test_a_measured_zero_is_not_the_same_as_no_data(signed_in, reference_data):
    """A food with an explicit 0.0 row has been measured, and its zero is real.

    This is the distinction that makes coverage worth having: `derived:plant-b12-zero`
    states that a plant food has no B12, which is a finding. An absent row states
    nothing at all.
    """
    signed_in.put("/profile", json=PROFILE)
    log_small_meal(signed_in, reference_data, TODAY)

    payload = signed_in.get(f"/targets/today?date={TODAY}").json()
    protein = nutrient(payload, "protein")
    thiamine = nutrient(payload, "thiamine")

    # Protein has a row and a real figure; thiamine has no row on this dish.
    assert protein["coverage"] == pytest.approx(1.0)
    assert thiamine["coverage"] == pytest.approx(0.0)


def test_the_tracking_endpoints_require_sign_in(api_client):
    assert api_client.get("/profile").status_code == 401
    assert api_client.get(f"/targets/today?date={TODAY}").status_code == 401
    assert api_client.get(f"/diary?date={TODAY}").status_code == 401
