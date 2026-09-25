"""The saved API key and the cached dish text, on the migrated schema.

A key is six columns that mean something only together, so the database refuses
a half-written one rather than trusting every writer to be careful. Each user has
one settings row, and one cached text per dish: those are the unique keys the
upserts in app.llm.service and app.planner.polish name as their conflict targets.
And both go with their user, the cached text with its dish too, so nothing a
user paid for outlives their account.
"""

import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from app.models.food import Dish
from app.models.llm import DishPolish, UserSettings
from app.models.user import User

SET_AT = datetime.datetime(2026, 9, 24, 9, 30, tzinfo=datetime.UTC)

# A complete key, as app.llm.service writes one. The ciphertext is a stand-in:
# the schema cannot tell a token from any other text, and does not need to.
KEY = {
    "llm_provider": "anthropic",
    "llm_model": "claude-opus-5",
    "llm_key_ciphertext": "gAAAAAB-stand-in-for-a-fernet-token",
    "llm_key_hint": "WXYZ",
    "llm_key_status": "ok",
    "llm_key_set_at": SET_AT,
}
NO_KEY = dict.fromkeys(KEY)


def make_user(db, name: str) -> User:
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    return user


def make_dish(db, code: str) -> Dish:
    dish = Dish(code=f"test:{code}", name=code.title(), source="authored")
    db.add(dish)
    db.flush()
    return dish


@pytest.fixture
def user(db) -> User:
    return make_user(db, "llm")


@pytest.fixture
def dish(db) -> Dish:
    return make_dish(db, "idli")


def polish(
    user: User, dish: Dish, description: str | None = "Soft steamed rice cakes."
) -> DishPolish:
    return DishPolish(
        user_id=user.id,
        dish_id=dish.id,
        brief_hash="a" * 64,
        description=description,
        cooking_note=None,
        model="claude-opus-5",
    )


def refused(db, *rows) -> None:
    db.add_all(rows)
    with pytest.raises(IntegrityError):
        db.flush()


def key_columns(db, user: User) -> list[tuple]:
    return [
        tuple(row)
        for row in db.execute(
            select(UserSettings.llm_key_ciphertext, UserSettings.llm_key_status).where(
                UserSettings.user_id == user.id
            )
        )
    ]


# --- user_settings -----------------------------------------------------------------


def test_a_complete_key_is_stored(db, user):
    db.add(UserSettings(user_id=user.id, **KEY))
    db.flush()

    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], "ok")]


def test_a_row_with_no_key_is_allowed(db, user):
    db.add(UserSettings(user_id=user.id))
    db.flush()

    assert key_columns(db, user) == [(None, None)]


def test_removing_a_key_nulls_it_and_keeps_the_row(db, user):
    row = UserSettings(user_id=user.id, **KEY)
    db.add(row)
    db.flush()

    for column, value in NO_KEY.items():
        setattr(row, column, value)
    db.flush()

    assert key_columns(db, user) == [(None, None)]


@pytest.mark.parametrize("missing", sorted(KEY))
def test_a_key_missing_any_one_column_is_refused(db, user, missing):
    refused(db, UserSettings(user_id=user.id, **{**KEY, missing: None}))


@pytest.mark.parametrize("present", sorted(KEY))
def test_one_key_column_on_its_own_is_refused(db, user, present):
    refused(db, UserSettings(user_id=user.id, **{**NO_KEY, present: KEY[present]}))


@pytest.mark.parametrize("status", ["ok", "rejected", "unreadable"])
def test_each_key_status_is_accepted(db, user, status):
    db.add(UserSettings(user_id=user.id, **{**KEY, "llm_key_status": status}))
    db.flush()

    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], status)]


@pytest.mark.parametrize("status", ["expired", "OK", ""])
def test_any_other_key_status_is_refused(db, user, status):
    refused(db, UserSettings(user_id=user.id, **{**KEY, "llm_key_status": status}))


def test_one_settings_row_per_user(db, user):
    db.add(UserSettings(user_id=user.id, **KEY))
    db.flush()
    refused(db, UserSettings(user_id=user.id))


def test_saving_a_key_again_replaces_it_in_place(db, user):
    """The service's upsert, which names the unique key as its conflict target."""

    def save(hint: str):
        return db.execute(
            insert(UserSettings)
            .values(user_id=user.id, **{**KEY, "llm_key_hint": hint})
            .on_conflict_do_update(constraint="uq_user_settings_user", set_={"llm_key_hint": hint})
            .returning(UserSettings.id)
        ).scalar_one()

    first = save("WXYZ")
    second = save("ABCD")

    assert second == first
    hints = db.scalars(
        select(UserSettings.llm_key_hint).where(UserSettings.user_id == user.id)
    ).all()
    assert hints == ["ABCD"]


# --- dish_polish ------------------------------------------------------------------


def test_one_cached_text_per_user_and_dish(db, user, dish):
    db.add(polish(user, dish))
    db.flush()
    refused(db, polish(user, dish, "Another take on the same dish."))


def test_another_user_or_another_dish_is_a_row_of_its_own(db, user, dish):
    other = make_user(db, "other")
    dosa = make_dish(db, "dosa")

    db.add_all([polish(user, dish), polish(other, dish), polish(user, dosa)])
    db.flush()

    rows = db.execute(
        select(DishPolish.user_id, DishPolish.dish_id).where(
            DishPolish.user_id.in_([user.id, other.id])
        )
    )
    assert {tuple(row) for row in rows} == {
        (user.id, dish.id),
        (other.id, dish.id),
        (user.id, dosa.id),
    }


def test_a_cached_text_needs_a_description(db, user, dish):
    refused(db, polish(user, dish, None))


def test_polishing_a_dish_again_replaces_its_text_in_place(db, user, dish):
    """The polish upsert, which names the unique key as its conflict target."""

    def save(brief_hash: str):
        return db.execute(
            insert(DishPolish)
            .values(
                user_id=user.id,
                dish_id=dish.id,
                brief_hash=brief_hash,
                description="Soft steamed rice cakes.",
                model="claude-opus-5",
            )
            .on_conflict_do_update(
                constraint="uq_dish_polish_user_dish", set_={"brief_hash": brief_hash}
            )
            .returning(DishPolish.id)
        ).scalar_one()

    first = save("a" * 64)
    second = save("b" * 64)

    assert second == first
    hashes = db.scalars(select(DishPolish.brief_hash).where(DishPolish.user_id == user.id)).all()
    assert hashes == ["b" * 64]


# --- cascades -----------------------------------------------------------------------


def test_the_key_and_the_cached_text_go_with_their_user(db, user, dish):
    user_id = user.id
    db.add_all([UserSettings(user_id=user.id, **KEY), polish(user, dish)])
    db.flush()

    db.delete(user)
    db.flush()

    assert db.scalars(select(UserSettings).where(UserSettings.user_id == user_id)).all() == []
    assert db.scalars(select(DishPolish).where(DishPolish.user_id == user_id)).all() == []


def test_the_cached_text_goes_with_its_dish(db, user, dish):
    dish_id = dish.id
    db.add_all([UserSettings(user_id=user.id, **KEY), polish(user, dish)])
    db.flush()

    db.delete(dish)
    db.flush()

    assert db.scalars(select(DishPolish).where(DishPolish.dish_id == dish_id)).all() == []
    # The key is the user's, not the dish's.
    assert key_columns(db, user) == [(KEY["llm_key_ciphertext"], "ok")]
