import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.main import app


@pytest.fixture
def api(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_in(api, monkeypatch, sub, email):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": email,
        },
    )
    api.post("/auth/google", json={"credential": "t"})


def test_create_and_read_a_household(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-a", "a@example.com")

    created = api.post("/households", json={"name": "Home"})
    assert created.status_code == 201

    mine = api.get("/households/me")
    assert mine.status_code == 200
    assert mine.json()["name"] == "Home"
    assert len(mine.json()["members"]) == 1
    assert mine.json()["members"][0]["share_health"] is False


def test_household_endpoints_require_sign_in(api):
    assert api.post("/households", json={"name": "Home"}).status_code == 401
    assert api.get("/households/me").status_code == 401


def test_me_returns_404_before_a_household_exists(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-b", "b@example.com")

    assert api.get("/households/me").status_code == 404


def test_creating_a_second_household_is_rejected(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-c", "c@example.com")
    api.post("/households", json={"name": "First"})

    assert api.post("/households", json={"name": "Second"}).status_code == 409


def test_an_invited_user_can_join(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-d", "d@example.com")
    api.post("/households", json={"name": "Home"})
    invite = api.post("/households/invites", json={"email": "guest@example.com"})
    assert invite.status_code == 201
    token = invite.json()["token"]

    api.post("/auth/logout")
    sign_in(api, monkeypatch, "sub-guest", "guest@example.com")
    accepted = api.post("/households/invites/accept", json={"token": token})

    assert accepted.status_code == 200
    assert len(api.get("/households/me").json()["members"]) == 2


def test_an_unknown_invite_token_is_rejected(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-e", "e@example.com")

    response = api.post("/households/invites/accept", json={"token": "nonsense"})

    assert response.status_code == 404


def test_leaving_returns_you_to_solo(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-g", "g@example.com")
    api.post("/households", json={"name": "Home"})

    assert api.post("/households/leave").status_code == 204
    assert api.get("/households/me").status_code == 404


def test_leaving_without_a_household_is_a_404(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-h", "h@example.com")

    assert api.post("/households/leave").status_code == 404


def test_visibility_can_be_updated(api, monkeypatch):
    sign_in(api, monkeypatch, "sub-f", "f@example.com")
    api.post("/households", json={"name": "Home"})

    response = api.patch("/households/visibility", json={"share_health": True})

    assert response.status_code == 200
    assert response.json()["share_health"] is True
    assert response.json()["share_progress"] is True
