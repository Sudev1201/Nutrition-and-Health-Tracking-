"""The weight API: weigh-ins in, a trend and the calorie target out.

Dates are relative to the real today, because a profile save records a weigh-in
dated today.
"""

import datetime
import zoneinfo

import pytest

from app.models.user import User
from app.models.weight import WeightLog
from app.planner import service as planner_service
from tests.test_tracking_api import PROFILE, nutrient

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
WEEK = planner_service.week_start_for(TODAY)


def days_ago(n: int) -> datetime.date:
    return TODAY - datetime.timedelta(days=n)


def take_a_step(api) -> dict:
    """Spec manual step 8 -- drift from the goal moves the target by a bounded step --
    with the third weigh-in a trend needs."""
    api.post("/weight", json={"weight_kg": 65.0, "date": str(days_ago(14))})
    api.post("/weight", json={"weight_kg": 65.5, "date": str(days_ago(7))})
    response = api.post("/weight", json={"weight_kg": 66.0})
    assert response.status_code == 201, response.text
    return response.json()


def test_weight_needs_a_session(api_client):
    assert api_client.get("/weight").status_code == 401


def test_weight_needs_a_profile(signed_in):
    assert signed_in.get("/weight").status_code == 404
    assert signed_in.post("/weight", json={"weight_kg": 70.0}).status_code == 404


def test_onboarding_records_the_first_weigh_in(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = signed_in.get("/weight").json()

    assert trend["weigh_ins"] == [{"date": str(TODAY), "weight_kg": 65.0}]
    assert trend["smoothed_kg"] == 65.0
    assert trend["observed_kg_per_week"] is None
    assert trend["adjustment"] is None
    assert "three weigh-ins" in trend["note"]


def test_saving_the_profile_again_does_not_duplicate_the_weigh_in(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.put("/profile", json=PROFILE)
    assert len(signed_in.get("/weight").json()["weigh_ins"]) == 1


def test_a_weigh_in_defaults_to_today_and_answers_with_the_trend(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    response = signed_in.post("/weight", json={"weight_kg": 64.4})

    assert response.status_code == 201
    assert response.json()["weigh_ins"][-1] == {"date": str(TODAY), "weight_kg": 64.4}


def test_a_weigh_in_moves_the_profile_weight(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/weight", json={"weight_kg": 64.4})
    assert signed_in.get("/profile").json()["weight_kg"] == 64.4


def test_a_weigh_in_cannot_be_dated_in_the_future(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    tomorrow = TODAY + datetime.timedelta(days=1)
    response = signed_in.post("/weight", json={"weight_kg": 64.0, "date": str(tomorrow)})
    assert response.status_code == 422


@pytest.mark.parametrize("kg", [7.4, 20.0, 301.0])
def test_an_implausible_weight_is_refused(signed_in, reference_data, kg):
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.post("/weight", json={"weight_kg": kg}).status_code == 422


def test_the_calorie_target_is_the_same_figure_today_shows(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = signed_in.get("/weight").json()
    energy = nutrient(signed_in.get(f"/targets/today?date={TODAY}").json(), "energy")

    assert trend["calorie_target_kcal"] == round(energy["rda"])
    assert trend["expected_kg_per_week"] == 0.0


def test_sustained_drift_moves_the_target_by_a_bounded_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    before = signed_in.get("/weight").json()["calorie_target_kcal"]

    trend = take_a_step(signed_in)

    assert trend["adjustment"]["delta_kcal"] == -210
    assert trend["adjustment"]["since"] == str(TODAY)
    assert "risen about 0.5 kg a week" in trend["adjustment"]["reason"]
    # The formula rose with the extra kilogram; the step sits on top, inside 10%.
    assert abs(trend["calorie_target_kcal"] - before) < 0.1 * before


def test_today_carries_the_recalibrated_target_and_says_so(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    trend = take_a_step(signed_in)
    today = signed_in.get(f"/targets/today?date={TODAY}").json()

    assert round(nutrient(today, "energy")["rda"]) == trend["calorie_target_kcal"]
    assert "calorie-recalibrated" in [w["kind"] for w in today["warnings"]]


def test_a_weigh_in_can_be_removed(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.post("/weight", json={"weight_kg": 64.0, "date": str(days_ago(7))})

    assert signed_in.delete(f"/weight/{days_ago(7)}").status_code == 204
    dates = [w["date"] for w in signed_in.get("/weight").json()["weigh_ins"]]
    assert dates == [str(TODAY)]


def test_removing_a_missing_weigh_in_is_not_found(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.delete(f"/weight/{days_ago(3)}").status_code == 404


def test_changing_the_goal_resets_the_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    take_a_step(signed_in)

    signed_in.put(
        "/profile", json={**PROFILE, "goal": "lose", "pace": "gentle", "weight_kg": 66.0}
    )

    trend = signed_in.get("/weight").json()
    assert trend["adjustment"] is None
    assert trend["goal"] == "lose"


def test_editing_something_else_keeps_the_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    take_a_step(signed_in)

    signed_in.put("/profile", json={**PROFILE, "weight_kg": 66.0, "conditions": ["prediabetes"]})

    assert signed_in.get("/weight").json()["adjustment"]["delta_kcal"] == -210


def test_a_step_and_its_removal_leave_the_stored_plan_alone(
    signed_in, reference_data, monkeypatch
):
    """Regenerating replaces every unlocked item, and a swap is not a lock: a weigh-in
    must never silently throw away the week the user customised."""
    signed_in.put("/profile", json=PROFILE)
    assert signed_in.get(f"/plan/week?start={WEEK}").status_code == 200
    calls = []
    monkeypatch.setattr(
        planner_service, "generate_week", lambda db, user, start, **kw: calls.append(start)
    )

    assert take_a_step(signed_in)["adjustment"] is not None
    signed_in.delete(f"/weight/{TODAY}")

    assert calls == []


def test_filling_in_a_past_week_takes_no_step(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)
    signed_in.delete(f"/weight/{TODAY}")
    for n, kg in ((21, 65.0), (14, 65.5), (7, 66.0)):
        response = signed_in.post("/weight", json={"weight_kg": kg, "date": str(days_ago(n))})
        assert response.status_code == 201

    assert signed_in.get("/weight").json()["adjustment"] is None


def test_another_users_weigh_ins_are_not_visible(signed_in, reference_data, db):
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(WeightLog(user_id=other.id, logged_on=days_ago(2), weight_kg=90.0))
    db.flush()

    signed_in.put("/profile", json=PROFILE)
    assert [w["weight_kg"] for w in signed_in.get("/weight").json()["weigh_ins"]] == [65.0]
