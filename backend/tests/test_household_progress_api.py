"""What a household sees of each member's week: counts of days on track, never targets.

Weekly progress is shared by default, so whoever cooks can see how the week went.
A target is health data -- a 1,500 mg sodium cap says hypertension, 8 mg of iron
says menopause -- so the household gets counts of days and nothing that names a
nutrient or a figure.

Last week is the one week certain to be over. Dates run from the real today,
because every profile save records a weigh-in dated today.

The fixture dish is 150 kcal, 4 g of protein and 30 mg of calcium per 100 g, and
measures nothing else, so a day of it measures exactly three nutrients. 1,600 g
is 2,400 kcal and 64 g of protein -- over the reference man's 2,105 kcal and his
42.9 g protein EAR -- but only 480 mg of calcium, under its 800 mg EAR: two of the
three are met. 50 g meets none of them. The two condition tests give it one more
figure each, so that a target only a condition sets has something to measure.
"""

import datetime
import zoneinfo

import pytest
from sqlalchemy import select

from app.auth import google as google_auth
from app.models.food import DishIngredient, IngredientNutrient
from app.models.nutrient import Nutrient
from app.planner import service as planner_service
from tests.conftest import NUTRIENTS
from tests.test_tracking_api import PROFILE

KOLKATA = zoneinfo.ZoneInfo("Asia/Kolkata")
TODAY = datetime.datetime.now(KOLKATA).date()
THIS_WEEK = planner_service.week_start_for(TODAY)
LAST_WEEK = THIS_WEEK - datetime.timedelta(days=7)

TWO_OF_THREE_GRAMS = 1600
NONE_OF_THREE_GRAMS = 50

# (sub, email, name). The tracker is the `signed_in` fixture's account.
TRACKER = ("sub-track", "track@example.com", "Tracker")
RAVI = ("sub-ravi", "ravi@example.com", "Ravi")

COUNT_KEYS = ("tracked_days", "nutrient_days_met", "nutrient_days_measured")
MEMBER_KEYS = {"user_id", "name", "is_me", "shared", *COUNT_KEYS}


def day(n: int) -> datetime.date:
    """Day n of last week; 0 is its Sunday."""
    return LAST_WEEK + datetime.timedelta(days=n)


def sign_in_as(api, monkeypatch, person: tuple[str, str, str]) -> None:
    """Switch the client to another Google account, as another phone would be."""
    sub, email, name = person
    identity = {"sub": sub, "email": email, "email_verified": True, "name": name}
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: identity,
    )
    api.post("/auth/logout")
    assert api.post("/auth/google", json={"credential": "t"}).status_code == 200


def eat(api, dish, on: datetime.date, grams: float) -> None:
    response = api.post(
        "/diary/entries",
        json={
            "date": str(on), "slot": "lunch", "food_id": str(dish.id),
            "food_kind": "dish", "grams": grams, "is_estimated": False,
        },
    )
    assert response.status_code == 201, response.text


def add_ravi(api, monkeypatch, dish, *, profile=PROFILE, meals=(), share_progress=True):
    """Invite Ravi. He joins, onboards unless `profile` is None, and logs `meals`
    ((date, grams) of the fixture dish); then the client is the tracker's again."""
    token = api.post("/households/invites", json={"email": RAVI[1]}).json()["token"]
    sign_in_as(api, monkeypatch, RAVI)
    assert api.post("/households/invites/accept", json={"token": token}).status_code == 200
    if profile is not None:
        assert api.put("/profile", json=profile).status_code == 200
    for on, grams in meals:
        eat(api, dish, on, grams)
    if not share_progress:
        response = api.patch("/households/visibility", json={"share_progress": False})
        assert response.status_code == 200
    sign_in_as(api, monkeypatch, TRACKER)


def progress(api, start: datetime.date = LAST_WEEK) -> dict:
    response = api.get(f"/households/progress?start={start}")
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, name: str) -> dict:
    return next(item for item in body["members"] if item["name"] == name)


def counts(item: dict) -> tuple:
    return tuple(item[key] for key in COUNT_KEYS)


def add_to_the_rice(db, dish, nutrient: Nutrient, per_100g: float) -> None:
    """Give the fixture dish's one ingredient a figure for `nutrient`."""
    rice = db.scalars(
        select(DishIngredient.ingredient_id).where(DishIngredient.dish_id == dish.id)
    ).one()
    db.add(
        IngredientNutrient(
            ingredient_id=rice, nutrient_id=nutrient.id, per_100g=per_100g, source="IFCT"
        )
    )
    db.flush()


@pytest.fixture
def api(signed_in, reference_data):
    """The tracker, onboarded, in a household of one."""
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    assert signed_in.post("/households", json={"name": "Home"}).status_code == 201
    return signed_in


def test_progress_needs_a_session(api_client):
    assert api_client.get(f"/households/progress?start={LAST_WEEK}").status_code == 401


def test_progress_needs_a_household(signed_in, reference_data):
    signed_in.put("/profile", json=PROFILE)

    response = signed_in.get(f"/households/progress?start={LAST_WEEK}")

    assert response.status_code == 404
    assert response.json()["detail"] == "You are not in a household yet"


def test_the_week_starts_on_a_sunday(api):
    response = api.get(f"/households/progress?start={day(1)}")

    assert response.status_code == 422
    assert response.json()["detail"] == "The week starts on a Sunday"


def test_a_week_not_yet_begun_is_refused(api):
    next_week = THIS_WEEK + datetime.timedelta(days=7)
    assert api.get(f"/households/progress?start={next_week}").status_code == 422


def test_you_see_your_own_week_as_counts(api, reference_data):
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    eat(api, reference_data, day(3), NONE_OF_THREE_GRAMS)
    me = api.get("/auth/me").json()["id"]

    assert progress(api) == {
        "start_date": str(LAST_WEEK),
        "members": [
            {
                "user_id": me,
                "name": "Tracker",
                "is_me": True,
                "shared": True,
                # Two days logged with three nutrients measured on each: six
                # nutrient-days, of which Sunday's energy and protein were on track.
                "tracked_days": 2,
                "nutrient_days_met": 2,
                "nutrient_days_measured": 6,
            }
        ],
    }


def test_the_counts_are_your_own_report_summed(api, reference_data):
    """One set of figures: with no condition adding a target, the household reads
    exactly the sums of the member's own report."""
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    eat(api, reference_data, day(3), NONE_OF_THREE_GRAMS)

    mine = row(progress(api), "Tracker")
    report = api.get(f"/reports/week?start={LAST_WEEK}").json()

    assert mine["tracked_days"] == report["tracked_days"]
    assert mine["nutrient_days_met"] == sum(n["days_met"] for n in report["nutrients"])
    assert mine["nutrient_days_measured"] == sum(
        n["measured_days"] for n in report["nutrients"]
    )


def test_a_member_sharing_progress_appears_with_counts(api, reference_data, monkeypatch):
    add_ravi(api, monkeypatch, reference_data, meals=[(day(1), TWO_OF_THREE_GRAMS)])

    body = progress(api)

    # You first, then the others.
    assert [item["name"] for item in body["members"]] == ["Tracker", "Ravi"]
    ravi = row(body, "Ravi")
    assert ravi["is_me"] is False
    assert ravi["shared"] is True
    assert counts(ravi) == (1, 2, 3)


def test_a_member_not_sharing_is_listed_without_figures(api, reference_data, monkeypatch):
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        meals=[(day(1), TWO_OF_THREE_GRAMS)],
        share_progress=False,
    )

    ravi = row(progress(api), "Ravi")

    assert ravi["shared"] is False
    assert counts(ravi) == (None, None, None)


def test_not_sharing_hides_you_from_the_household_but_not_from_yourself(
    api, reference_data, monkeypatch
):
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(api, monkeypatch, reference_data)
    assert api.patch("/households/visibility", json={"share_progress": False}).status_code == 200

    mine = row(progress(api), "Tracker")
    assert mine["shared"] is True
    assert counts(mine) == (1, 2, 3)

    sign_in_as(api, monkeypatch, RAVI)
    body = progress(api)
    assert body["members"][0]["name"] == "Ravi"
    assert body["members"][0]["is_me"] is True
    # A week with nothing logged is zero days, not unknown.
    assert counts(body["members"][0]) == (0, 0, 0)
    tracker = row(body, "Tracker")
    assert tracker["shared"] is False
    assert counts(tracker) == (None, None, None)


def test_a_member_without_a_profile_has_no_figures(api, reference_data, monkeypatch):
    add_ravi(api, monkeypatch, reference_data, profile=None)

    ravi = row(progress(api), "Ravi")

    assert ravi["shared"] is True
    assert counts(ravi) == (None, None, None)


def test_nothing_names_a_nutrient_or_a_target(api, reference_data, monkeypatch):
    """Both have hypertension, whose 1,500 mg sodium cap would say so on its own."""
    hypertensive = {**PROFILE, "conditions": ["hypertension"]}
    assert api.put("/profile", json=hypertensive).status_code == 200
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        profile=hypertensive,
        meals=[(day(2), TWO_OF_THREE_GRAMS)],
    )

    response = api.get(f"/households/progress?start={LAST_WEEK}")
    body = response.json()

    assert set(body) == {"start_date", "members"}
    for item in body["members"]:
        assert set(item) == MEMBER_KEYS
        # Small whole numbers of days, with no room left for a figure like 1,500 mg.
        assert counts(item) == (1, 2, 3)
    text = response.text.lower()
    for code, display_name, *_ in NUTRIENTS:
        assert code not in text
        assert display_name.lower() not in text
    assert "kcal" not in text
    assert "mg" not in text


def test_a_target_only_a_condition_sets_adds_no_nutrient_days(api, reference_data, db):
    """High cholesterol sets a cholesterol ceiling that no other profile has. Counted,
    it would add a nutrient-day to every logged day, and a household eating the same
    food would read the diagnosis off the difference."""
    cholesterol = Nutrient(
        code="cholesterol",
        display_name="Cholesterol",
        unit="mg",
        category="macro",
        is_compensable=False,
        compensation_days=0,
        is_excess_sensitive=True,
    )
    db.add(cholesterol)
    db.flush()
    # IFCT gives every food a cholesterol figure, zero for plants, and a zero still measures.
    add_to_the_rice(db, reference_data, cholesterol, 0.0)
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    assert counts(row(progress(api), "Tracker")) == (1, 2, 3)

    profile = {**PROFILE, "conditions": ["high_cholesterol"]}
    assert api.put("/profile", json=profile).status_code == 200

    # The member's own report carries the ceiling, measured and met...
    report = api.get(f"/reports/week?start={LAST_WEEK}").json()
    assert "cholesterol" in {n["code"] for n in report["nutrients"]}
    # ...and the household's counts are what they were without the condition.
    assert counts(row(progress(api), "Tracker")) == (1, 2, 3)


def test_hypertension_from_sixty_adds_no_nutrient_days(api, reference_data, db, monkeypatch):
    """From 60 the reference rows carry no potassium, so hypertension adds a potassium
    target nobody else of that age has. Counted, it would add a nutrient-day to every
    logged day and say who has high blood pressure."""
    potassium = db.scalars(select(Nutrient).where(Nutrient.code == "potassium")).one()
    add_to_the_rice(db, reference_data, potassium, 100.0)
    elder = {**PROFILE, "age": 65}
    assert api.put("/profile", json=elder).status_code == 200
    eat(api, reference_data, day(0), TWO_OF_THREE_GRAMS)
    add_ravi(
        api,
        monkeypatch,
        reference_data,
        profile={**elder, "conditions": ["hypertension"]},
        meals=[(day(0), TWO_OF_THREE_GRAMS)],
    )

    body = progress(api)

    # Without the filter Ravi's potassium, measured and short, reads one more.
    assert counts(row(body, "Ravi")) == counts(row(body, "Tracker"))


def test_the_day_in_progress_is_not_counted(api, reference_data):
    """Today's lunch is part of a day, not a day. It counts once the day is over."""
    eat(api, reference_data, TODAY, TWO_OF_THREE_GRAMS)

    mine = row(progress(api, start=THIS_WEEK), "Tracker")

    assert counts(mine) == (0, 0, 0)
