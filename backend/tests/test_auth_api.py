import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.config import settings
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


# --- logout deletes the cookie it set ------------------------------------------------
#
# A browser replaces a cookie only with a Set-Cookie it accepts. Under a __Host-
# or __Secure- name, one without Secure is rejected outright, so a bare deletion
# would leave the session in place. The deletion carries what the sign-in set.


def _flags(response) -> set[str]:
    """The attributes of the response's one Set-Cookie, less its value and lifetime."""
    _, *attributes = (part.strip() for part in response.headers["set-cookie"].split(";"))
    return {
        attribute
        for attribute in attributes
        if not attribute.lower().startswith(("expires=", "max-age="))
    }


def test_logout_deletes_the_cookie_with_the_attributes_it_was_set_with(api, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    _accept_google_token(monkeypatch)
    sign_in = api.post("/auth/google", json={"credential": "t"})

    logout = api.post("/auth/logout")

    assert logout.status_code == 204
    header = logout.headers["set-cookie"]
    assert header.startswith(f"{settings.session_cookie_name}=")
    assert "Max-Age=0" in header
    assert {"HttpOnly", "SameSite=lax", "Secure"} <= _flags(logout)
    assert _flags(logout) == _flags(sign_in)


def test_a_development_logout_matches_a_development_sign_in(api, monkeypatch):
    # Set explicitly: a developer's backend/.env may turn COOKIE_SECURE on.
    monkeypatch.setattr(settings, "cookie_secure", False)
    _accept_google_token(monkeypatch)
    sign_in = api.post("/auth/google", json={"credential": "t"})

    logout = api.post("/auth/logout")

    assert "Secure" not in _flags(logout)
    assert _flags(logout) == _flags(sign_in)
