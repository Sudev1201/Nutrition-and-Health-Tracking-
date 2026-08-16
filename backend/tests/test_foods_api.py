import pytest
from fastapi.testclient import TestClient

from app.auth import google as google_auth
from app.db import get_db
from app.foods import service
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


def test_ingredients_are_reachable_even_when_dishes_fill_the_limit(db, api, monkeypatch):
    """THE BUG: dishes were queried up to `limit`, ingredients appended, and
    the concatenation truncated back to `limit` -- so once `limit` dishes
    matched, no ingredient was ever returned. "rice" matched 30 dishes and 7
    ingredients and returned 0 ingredients, which put `ifct:A015 Rice, raw,
    milled` out of reach of the only search endpoint on the branch.
    """
    seed_nutrients(db)
    for index in range(30):
        db.add(
            Dish(
                code=f"si:rice_dish_{index}",
                name=f"Rice dish {index}",
                source="authored",
                is_editable=True,
            )
        )
    db.add(Ingredient(code="ifct:A015", name="Rice, raw, milled", source="IFCT"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=rice&limit=20").json()

    assert len(results) == 20
    assert any(r["name"] == "Rice, raw, milled" for r in results)
    assert sum(1 for r in results if r["kind"] == "dish") == 19


def test_search_splits_the_limit_when_both_kinds_match_in_bulk(db, api, monkeypatch):
    seed_nutrients(db)
    for index in range(30):
        db.add(
            Dish(code=f"si:d{index}", name=f"Milk dish {index}", source="authored",
                 is_editable=True)
        )
        db.add(Ingredient(code=f"ifct:X{index}", name=f"Milk item {index}", source="IFCT"))
    db.flush()
    sign_in(api, monkeypatch)

    results = api.get("/foods/search?q=milk&limit=20").json()

    kinds = [r["kind"] for r in results]
    assert kinds.count("dish") == 10
    assert kinds.count("ingredient") == 10


def test_a_whitespace_only_query_is_rejected(db, api, monkeypatch):
    """`Query(min_length=1)` admits " ", which strips to "" and makes the LIKE
    pattern "%%" -- twenty arbitrary dishes returned as if they matched."""
    seed_nutrients(db)
    db.add(Dish(code="si:idli", name="Idli", source="authored", is_editable=True))
    db.flush()
    sign_in(api, monkeypatch)

    assert api.get("/foods/search?q=%20").status_code == 422
    assert api.get("/foods/search?q=%20%20%09").status_code == 422


def test_the_service_refuses_a_blank_query_to_any_caller(db):
    """Not only the router: plan 5's diary calls the service directly."""
    seed_nutrients(db)

    with pytest.raises(service.EmptySearchQuery):
        service.search_foods(db, "   ")
