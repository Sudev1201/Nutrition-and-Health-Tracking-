"""Re-encrypting the stored API keys under the keyring's first key: scripts.rotate_llm_keys.

Rotation is how an old encryption key is retired. The new key goes first in
LLM_KEY_ENCRYPTION_KEYS, the script moves every row onto it, and the old key can then be
removed without anyone losing their saved key.
"""

import contextlib

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.llm import crypto, service
from app.llm.providers import DEFAULT_MODEL
from app.models.llm import UserSettings
from app.models.user import User
from scripts import rotate_llm_keys
from tests.conftest import FakeProvider

KEY_A = "sk-ant-api03-" + "a" * 40 + "AAAA"
KEY_B = "sk-ant-api03-" + "b" * 40 + "BBBB"
KEY_C = "sk-ant-api03-" + "c" * 40 + "CCCC"


def fresh_key() -> str:
    return Fernet.generate_key().decode()


def user_with_key(db, name: str, api_key: str) -> User:
    """A user who saved `api_key` under whatever keyring is set now."""
    user = User(google_sub=f"sub-{name}", email=f"{name}@example.com", name=name)
    db.add(user)
    db.flush()
    service.save_key(db, user, api_key=api_key, model=DEFAULT_MODEL, provider=FakeProvider())
    return user


def stored(db, user: User) -> UserSettings:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one()


@pytest.fixture
def script_session(db, monkeypatch):
    """The script's session, pointed at the test transaction instead of the dev database."""

    @contextlib.contextmanager
    def session():
        yield db

    monkeypatch.setattr(rotate_llm_keys, "SessionLocal", session)


def test_keys_under_an_old_key_move_to_the_first(db, set_keyring):
    old, new = fresh_key(), fresh_key()
    set_keyring(old)
    asha = user_with_key(db, "asha", KEY_A)
    ravi = user_with_key(db, "ravi", KEY_B)
    set_keyring(new, old)

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=2, current=0, unreadable=0)
    assert crypto.is_current(stored(db, asha).llm_key_ciphertext)
    # With the old key gone, each still decrypts, for its own user.
    set_keyring(new)
    assert service.key_for(db, asha) == (KEY_A, DEFAULT_MODEL)
    assert service.key_for(db, ravi) == (KEY_B, DEFAULT_MODEL)


def test_a_second_run_finds_every_key_current(db, set_keyring):
    old, new = fresh_key(), fresh_key()
    set_keyring(old)
    asha = user_with_key(db, "asha", KEY_A)
    user_with_key(db, "ravi", KEY_B)
    set_keyring(new, old)
    # Saved after the new key went first, so under it already.
    user_with_key(db, "meena", KEY_C)

    assert service.rotate_all(db) == service.RotationCounts(rotated=2, current=1, unreadable=0)
    rotated = stored(db, asha).llm_key_ciphertext

    assert service.rotate_all(db) == service.RotationCounts(rotated=0, current=3, unreadable=0)
    # A current key is left as it is, not encrypted again.
    assert stored(db, asha).llm_key_ciphertext == rotated


def test_a_key_nothing_in_the_keyring_can_read_is_marked_and_left(db, set_keyring):
    set_keyring(fresh_key())
    asha = user_with_key(db, "asha", KEY_A)
    before = stored(db, asha).llm_key_ciphertext
    # The key it was saved under is gone: removed before rotating.
    set_keyring(fresh_key())

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=0, current=0, unreadable=1)
    row = stored(db, asha)
    assert row.llm_key_status == "unreadable"
    assert row.llm_key_ciphertext == before
    # Its owner is asked for the key again, and nothing tries to use it meanwhile.
    assert service.summary(db, asha).status == "unreadable"
    assert service.key_for(db, asha) is None


def test_a_key_copied_from_another_user_is_not_rotated_into_their_row(db, set_keyring):
    old, new = fresh_key(), fresh_key()
    set_keyring(old)
    asha = user_with_key(db, "asha", KEY_A)
    ravi = user_with_key(db, "ravi", KEY_B)
    copied = stored(db, asha).llm_key_ciphertext
    stored(db, ravi).llm_key_ciphertext = copied
    db.flush()
    set_keyring(new, old)

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=1, current=0, unreadable=1)
    assert stored(db, ravi).llm_key_status == "unreadable"
    assert stored(db, ravi).llm_key_ciphertext == copied
    assert service.key_for(db, asha) == (KEY_A, DEFAULT_MODEL)


def test_a_current_key_copied_from_another_user_is_marked(db, set_keyring):
    """A token already under the first key still has its user binding checked."""
    set_keyring(fresh_key())
    asha = user_with_key(db, "asha", KEY_A)
    ravi = user_with_key(db, "ravi", KEY_B)
    copied = stored(db, asha).llm_key_ciphertext
    stored(db, ravi).llm_key_ciphertext = copied
    db.flush()
    assert crypto.is_current(copied)

    counts = service.rotate_all(db)

    assert counts == service.RotationCounts(rotated=0, current=1, unreadable=1)
    assert stored(db, ravi).llm_key_status == "unreadable"
    assert stored(db, ravi).llm_key_ciphertext == copied
    assert service.key_for(db, ravi) is None
    assert service.key_for(db, asha) == (KEY_A, DEFAULT_MODEL)


def test_the_script_rotates_and_reports(db, set_keyring, capsys, script_session):
    old, new = fresh_key(), fresh_key()
    set_keyring(old)
    asha = user_with_key(db, "asha", KEY_A)
    set_keyring(new, old)

    assert rotate_llm_keys.main() == 0

    assert capsys.readouterr().out == "rotated 1, current 0, unreadable 0\n"
    assert crypto.is_current(stored(db, asha).llm_key_ciphertext)


def test_the_script_refuses_without_a_keyring(set_keyring, monkeypatch, capsys):
    set_keyring()

    def no_session():
        raise AssertionError("the script opened a database session")

    monkeypatch.setattr(rotate_llm_keys, "SessionLocal", no_session)

    assert rotate_llm_keys.main() == 1
    assert "LLM_KEY_ENCRYPTION_KEYS is not set" in capsys.readouterr().err
