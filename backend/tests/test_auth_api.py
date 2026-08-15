import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def api(db) -> TestClient:
    """A client whose requests run inside the test transaction."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _accept_google_token(monkeypatch, sub="sub-1", email="person@example.com", name="A Person"):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": sub,
            "email": email,
            "email_verified": True,
            "name": name,
        },
    )


def test_sign_in_creates_a_user_and_sets_a_cookie(api, db, monkeypatch):
    _accept_google_token(monkeypatch)

    response = api.post("/auth/google", json={"credential": "google-token"})

    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"
    assert "hm_session" in response.cookies
    assert db.query(User).filter_by(google_sub="sub-1").one().name == "A Person"


def test_signing_in_twice_reuses_the_same_user(api, db, monkeypatch):
    _accept_google_token(monkeypatch)
    first = api.post("/auth/google", json={"credential": "t"}).json()

    _accept_google_token(monkeypatch, name="A Renamed Person")
    second = api.post("/auth/google", json={"credential": "t"}).json()

    assert first["id"] == second["id"]
    assert db.query(User).count() == 1
    assert second["name"] == "A Renamed Person"


def test_rejects_an_untrusted_google_token(api, monkeypatch):
    def explode(token, request, audience):
        raise ValueError("bad audience")

    monkeypatch.setattr(google_auth.google_id_token, "verify_oauth2_token", explode)

    response = api.post("/auth/google", json={"credential": "nope"})

    assert response.status_code == 401


def test_me_returns_the_signed_in_user(api, monkeypatch):
    _accept_google_token(monkeypatch)
    api.post("/auth/google", json={"credential": "t"})

    response = api.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "person@example.com"


def test_me_requires_a_session(api):
    response = api.get("/auth/me")

    assert response.status_code == 401


def test_logout_clears_the_session(api, monkeypatch):
    _accept_google_token(monkeypatch)
    api.post("/auth/google", json={"credential": "t"})

    api.post("/auth/logout")

    assert api.get("/auth/me").status_code == 401
