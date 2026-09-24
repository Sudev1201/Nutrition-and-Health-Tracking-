"""The cycle API -- and the two rules a well-meaning change would get wrong.

THE TWO COUNTER-INTUITIVE RULES, LOCKED IN.

1. Logging a period must leave the iron target exactly where it was. ICMR's
   29 mg/day for women ALREADY averages menstrual loss across the cycle, so
   raising it on bleed days counts that loss twice. The giveaway is ICMR's
   pregnancy RDA, 27 mg: lower than the non-pregnant figure, which only makes
   sense if menstruation is baked into the 29. Offsetting the loss in real time
   would take ~37 mg of extra dietary iron a day anyway, and hepcidin already
   raises absorption during menses.

2. Cycle phase must never move the calorie target. The luteal rise in resting
   expenditure is ~32 kcal/day once anovulatory cycles are counted -- inside the
   noise of intake -- and an app that expects more eating in the luteal phase
   manufactures the logging pattern that would seem to prove it right.

Both are exactly what a future change would "helpfully" fix. These tests stop it.
"""

import ast
import datetime
import pathlib
import zoneinfo

from app.models.cycle import CycleLog
from app.models.user import User
from tests.test_tracking_api import PROFILE, nutrient

TODAY = datetime.date(2026, 8, 17)
REAL_TODAY = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata")).date()

WOMAN = {**PROFILE, "sex": "female", "weight_kg": 55.0, "menstrual_status": "menstruating"}
ALL_NO = {
    "soaks_within_two_hours": False,
    "longer_than_seven_days": False,
    "large_clots": False,
    "flooding": False,
}

CYCLE_TABLE_MODULES = ("app.cycle", "app.models.cycle")
CYCLE_MODELS = {"CycleLog", "CycleScreening", "CycleSettings", "CycleSymptom"}


def on(offset: int) -> datetime.date:
    return TODAY + datetime.timedelta(days=offset)


def cycle(api, date: datetime.date = TODAY) -> dict:
    response = api.get(f"/cycle?date={date}")
    assert response.status_code == 200, response.text
    return response.json()


def tracking(api, profile: dict = WOMAN):
    assert api.put("/profile", json=profile).status_code == 200
    assert api.patch("/cycle", json={"enabled": True}).status_code == 200
    return api


def log(api, date: datetime.date, flow: str | None = None, *symptoms: str):
    response = api.put(f"/cycle/days/{date}", json={"flow": flow, "symptoms": list(symptoms)})
    assert response.status_code == 200, response.text


def note_ids(state: dict) -> list[str]:
    return [note["id"] for note in state["coaching"]]


# --- access ---------------------------------------------------------------------------------


def test_cycle_needs_a_session(api_client):
    assert api_client.get("/cycle").status_code == 401


def test_cycle_needs_a_profile(signed_in):
    assert signed_in.get("/cycle").status_code == 404


def test_a_man_is_not_offered_cycle_tracking(signed_in):
    signed_in.put("/profile", json=PROFILE)
    state = cycle(signed_in)

    assert state["eligible"] is False
    assert state["ineligible_reason"] == "not-female"
    assert signed_in.patch("/cycle", json={"enabled": True}).status_code == 409


def test_nor_is_a_woman_after_menopause(signed_in):
    signed_in.put("/profile", json={**WOMAN, "menstrual_status": "postmenopausal"})

    assert cycle(signed_in)["ineligible_reason"] == "postmenopausal"
    assert signed_in.patch("/cycle", json={"enabled": True}).status_code == 409


def test_another_users_cycle_data_is_invisible(signed_in, db):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(CycleLog(user_id=other.id, logged_on=on(-1), flow="heavy"))
    db.flush()

    tracking(signed_in)
    assert cycle(signed_in)["days"] == []


# --- the switch -----------------------------------------------------------------------------


def test_tracking_is_off_until_turned_on(signed_in):
    signed_in.put("/profile", json=WOMAN)
    state = cycle(signed_in)

    assert state["eligible"] is True
    assert state["enabled"] is False
    assert state["coaching"] == []


def test_turning_it_on_brings_the_coaching(signed_in):
    state = cycle(tracking(signed_in))

    assert state["enabled"] is True
    assert note_ids(state) == ["coffee-timing", "calcium"]
    assert all(note["evidence"] for note in state["coaching"])


def test_nothing_is_logged_while_tracking_is_off(signed_in):
    signed_in.put("/profile", json=WOMAN)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": "medium", "symptoms": []})
    assert response.status_code == 409


def test_turning_it_off_hides_the_log_but_keeps_it(signed_in):
    log(tracking(signed_in), on(-1), "medium")

    signed_in.patch("/cycle", json={"enabled": False})
    assert cycle(signed_in)["days"] == []

    signed_in.patch("/cycle", json={"enabled": True})
    assert len(cycle(signed_in)["days"]) == 1


def test_history_left_behind_by_a_profile_change_can_still_be_erased(signed_in):
    log(tracking(signed_in), on(-1), "medium")
    signed_in.put("/profile", json={**WOMAN, "menstrual_status": "postmenopausal"})

    state = cycle(signed_in)
    assert state["eligible"] is False
    assert state["days"] == []
    assert state["has_history"] is True

    assert signed_in.delete("/cycle").status_code == 204
    assert cycle(signed_in)["has_history"] is False


def test_erasing_removes_everything(signed_in):
    log(tracking(signed_in), on(-1), "medium", "cramps")
    signed_in.post("/cycle/screening", json={**ALL_NO, "date": str(TODAY)})

    assert signed_in.delete("/cycle").status_code == 204
    assert cycle(signed_in)["enabled"] is False

    signed_in.patch("/cycle", json={"enabled": True})
    state = cycle(signed_in)
    assert state["days"] == []
    assert state["screening"] is None


# --- logging days ---------------------------------------------------------------------------


def test_a_day_is_logged_and_read_back(signed_in):
    log(tracking(signed_in), on(-1), "medium", "cramps", "bloating")
    state = cycle(signed_in)

    assert state["days"] == [
        {"date": str(on(-1)), "flow": "medium", "symptoms": ["bloating", "cramps"]}
    ]
    assert state["last_period_start"] == str(on(-1))


def test_days_come_newest_first(signed_in):
    tracking(signed_in)
    log(signed_in, on(-2), "light")
    log(signed_in, on(-1), "medium")
    assert [d["date"] for d in cycle(signed_in)["days"]] == [str(on(-1)), str(on(-2))]


def test_logging_a_day_again_replaces_it(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium", "cramps")
    log(signed_in, on(-1), "heavy")

    assert cycle(signed_in)["days"] == [{"date": str(on(-1)), "flow": "heavy", "symptoms": []}]


def test_a_symptom_can_be_logged_without_bleeding(signed_in):
    log(tracking(signed_in), on(-3), None, "bloating")
    state = cycle(signed_in)

    assert state["days"][0]["flow"] is None
    assert state["last_period_start"] is None


def test_an_empty_day_clears_it(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium")
    log(signed_in, on(-1))
    assert cycle(signed_in)["days"] == []


def test_a_day_can_be_removed(signed_in):
    log(tracking(signed_in), on(-1), "medium")

    assert signed_in.delete(f"/cycle/days/{on(-1)}").status_code == 204
    assert signed_in.delete(f"/cycle/days/{on(-1)}").status_code == 404


def test_a_future_day_is_refused(signed_in):
    tracking(signed_in)
    tomorrow = REAL_TODAY + datetime.timedelta(days=1)
    response = signed_in.put(f"/cycle/days/{tomorrow}", json={"flow": "light", "symptoms": []})
    assert response.status_code == 422


def test_cravings_are_not_a_symptom_here(signed_in):
    tracking(signed_in)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": None, "symptoms": ["cravings"]})
    assert response.status_code == 422


def test_an_unknown_flow_is_refused(signed_in):
    tracking(signed_in)
    response = signed_in.put(f"/cycle/days/{on(-1)}", json={"flow": "spotting", "symptoms": []})
    assert response.status_code == 422


# --- coaching and referral ------------------------------------------------------------------


def test_ginger_follows_cramps_early_in_a_bleed_only(signed_in):
    tracking(signed_in)
    log(signed_in, on(-1), "medium", "cramps")
    log(signed_in, on(0), "heavy")

    assert "ginger" in note_ids(cycle(signed_in, TODAY))
    assert "ginger" not in note_ids(cycle(signed_in, on(3)))


def test_a_yes_on_the_screening_refers_to_a_clinician(signed_in):
    tracking(signed_in)
    response = signed_in.post(
        "/cycle/screening",
        json={**ALL_NO, "soaks_within_two_hours": True, "date": str(TODAY)},
    )
    assert response.status_code == 200

    state = cycle(signed_in)
    assert "two hours" in state["referral"]["reason"]
    assert state["screening"]["soaks_within_two_hours"] is True


def test_answering_no_again_withdraws_the_referral(signed_in):
    tracking(signed_in)
    signed_in.post("/cycle/screening", json={**ALL_NO, "flooding": True, "date": str(on(-7))})
    signed_in.post("/cycle/screening", json={**ALL_NO, "date": str(TODAY)})
    assert cycle(signed_in)["referral"] is None


def test_eight_days_in_a_row_refers_to_a_clinician(signed_in):
    tracking(signed_in)
    for offset in range(-8, 0):
        log(signed_in, on(offset), "medium")
    assert "8 days in a row" in cycle(signed_in)["referral"]["reason"]


def test_heavy_flow_alone_does_not_refer(signed_in):
    tracking(signed_in)
    for offset in range(-3, 0):
        log(signed_in, on(offset), "heavy")
    assert cycle(signed_in)["referral"] is None


def test_screening_needs_tracking_on(signed_in):
    signed_in.put("/profile", json=WOMAN)
    assert signed_in.post("/cycle/screening", json=ALL_NO).status_code == 409


# --- THE LOCKED RULES -----------------------------------------------------------------------


def targets(api, date: datetime.date) -> dict:
    response = api.get(f"/targets/today?date={date}")
    assert response.status_code == 200, response.text
    return response.json()


def the_heaviest_cycle_there_is(api):
    """Heavy bleeding with cramps for three days, and a yes to every screening question."""
    for offset in range(-2, 1):
        log(api, on(offset), "heavy", "cramps", "bloating")
    yes = dict.fromkeys(ALL_NO, True)
    assert api.post("/cycle/screening", json={**yes, "date": str(TODAY)}).status_code == 200


def test_logging_a_period_does_not_raise_the_iron_target(signed_in, iron_reference):
    tracking(signed_in)
    before = nutrient(targets(signed_in, TODAY), "iron")

    the_heaviest_cycle_there_is(signed_in)

    after = nutrient(targets(signed_in, TODAY), "iron")
    assert after["rda"] == before["rda"] == 29
    assert after["target_effective"] == before["target_effective"]
    # The referral is the answer to heavy bleeding -- not a raised iron goal.
    assert cycle(signed_in)["referral"] is not None


def test_cycle_phase_never_moves_the_calorie_target(signed_in, iron_reference):
    tracking(signed_in)
    dates = [on(-2), TODAY, on(7), on(14), on(21)]  # bleed days, follicular, luteal
    before = {d: nutrient(targets(signed_in, d), "energy") for d in dates}

    the_heaviest_cycle_there_is(signed_in)

    for d in dates:
        after = nutrient(targets(signed_in, d), "energy")
        assert after["rda"] == before[d]["rda"]
        assert after["target_effective"] == before[d]["target_effective"]


def test_nothing_in_the_targets_path_imports_cycle_code():
    """The rule is structural: the modules that compute targets never see cycle data."""
    app = pathlib.Path(__file__).resolve().parent.parent / "app"
    paths = [
        path
        for package in ("nutrition_core", "targets", "planner", "weight")
        for path in (app / package).glob("*.py")
    ]
    assert paths

    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                modules, names = [alias.name for alias in node.names], []
            elif isinstance(node, ast.ImportFrom):
                modules, names = [node.module or ""], [alias.name for alias in node.names]
            else:
                continue
            assert not any(m.startswith(CYCLE_TABLE_MODULES) for m in modules), path
            assert not CYCLE_MODELS & set(names), path
