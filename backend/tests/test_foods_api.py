import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.main import app
from app.models.food import Dish, Ingredient
from etl.load_nutrients import seed_nutrients


@pytest.fixture
def api(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def sign_in(api, monkeypatch):
    monkeypatch.setattr(
        google_auth.google_id_token,
        "verify_oauth2_token",
        lambda token, request, audience: {
            "sub": "s1", "email": "a@example.com", "email_verified": True, "name": "A"
        },
    )
    api.post("/auth/google", json={"credential": "t"})


def test_search_finds_dishes_and_ingredients(db, api, monkeypatch):
    seed_nutrients(db)
    db.add(Dish(code="si:idli", name="Idli", source="authored", is_editable=True))
    db.add(Ingredient(code="ifct:A001", name="Amaranth seed", source="IFCT",
                      search_aliases="Tam. Keerai vidai"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=idli").json()

    assert any(r["name"] == "Idli" and r["kind"] == "dish" for r in results)


def test_search_matches_regional_aliases(db, api, monkeypatch):
    seed_nutrients(db)
    db.add(Ingredient(code="ifct:A001", name="Amaranth seed", source="IFCT",
                      search_aliases="Tam. Keerai vidai"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=keerai").json()

    assert any(r["name"] == "Amaranth seed" for r in results)


def test_search_requires_sign_in(api):
    assert api.get("/foods/search?q=idli").status_code == 401
