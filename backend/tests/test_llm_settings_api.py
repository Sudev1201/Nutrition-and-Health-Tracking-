"""The user's own Anthropic API key, over HTTP: checked, stored encrypted, never returned.

PUT checks the key with the provider before anything is written, then stores it encrypted
and bound to its user. GET never decrypts and shows only the last four characters. Every
key here is an obvious fake, and no test reaches Anthropic: `fake_provider` stands in.
"""

import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import google as google_auth
from app.llm import crypto, service
from app.llm.providers import KeyRejected, ModelUnavailable, NoCredit, ProviderUnavailable
from app.main import app
from app.models.llm import UserSettings
from app.models.user import User
from app.profiles import service as profiles
from tests.conftest import sql_statements
from tests.test_tracking_api import PROFILE

KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
OTHER_KEY = "sk-ant-api03-" + "y" * 40 + "ABCD"
# The frontend's model list, default first.
OFFERED = ["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"]
FORMAT_MESSAGE = "That doesn't look like an Anthropic API key"
# Task 1's answer to a malformed keyring: fixed, so no part of the keyring reaches a log.
MALFORMED_KEYRING = "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"


def put_key(client, api_key: str = KEY, model: str = "claude-opus-5"):
    return client.put("/settings/llm", json={"api_key": api_key, "model": model})


def read(client) -> dict:
    return client.get("/settings/llm").json()


def the_row(db, user: User) -> UserSettings | None:
    return db.scalars(select(UserSettings).where(UserSettings.user_id == user.id)).one_or_none()


def sign_in_as(client, monkeypatch, sub: str, email: str) -> None:
    """Sign out, then in again as someone else, on the same client."""
    client.post("/auth/logout")
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
    client.post("/auth/google", json={"credential": "t"})


@pytest.fixture
def me(signed_in, db) -> User:
    return db.scalar(select(User).where(User.email == "track@example.com"))


# --- reading ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "body"),
    [("GET", None), ("PUT", {"api_key": KEY, "model": "claude-opus-5"}), ("DELETE", None)],
)
def test_the_key_routes_need_a_session(api_client, method, body):
    response = api_client.request(method, "/settings/llm", json=body)

    assert response.status_code == 401
    # The shared auth dependency answers before any handler here runs, so this is the one
    # answer without no-store. Its body is fixed: nothing of the request, and no key.
    assert response.json() == {"detail": "Not signed in"}


def test_before_any_key_there_is_nothing_to_show(signed_in, llm_keyring):
    response = signed_in.get("/settings/llm")

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "provider": None,
        "model": None,
        "key_hint": None,
        "status": "none",
        "models": OFFERED,
    }


def test_without_a_keyring_the_feature_is_off(signed_in, set_keyring, fake_provider, db, me):
    set_keyring()

    assert read(signed_in) == {
        "available": False,
        "provider": None,
        "model": None,
        "key_hint": None,
        "status": "none",
        "models": OFFERED,
    }

    response = put_key(signed_in)

    assert response.status_code == 503
    assert response.json() == {"detail": "AI descriptions are not set up on this server"}
    # A key this server cannot store is never sent to Anthropic.
    assert fake_provider.checked == []
    assert the_row(db, me) is None


# --- saving ----------------------------------------------------------------------------


def test_a_key_is_checked_then_stored_encrypted(signed_in, llm_keyring, fake_provider, db, me):
    response = put_key(signed_in, model="claude-sonnet-5")

    assert response.status_code == 200
    # Exactly these six fields: nothing that is, or could be turned back into, the key.
    assert response.json() == {
        "available": True,
        "provider": "anthropic",
        "model": "claude-sonnet-5",
        "key_hint": "WXYZ",
        "status": "ok",
        "models": OFFERED,
    }
    assert KEY not in response.text
    assert fake_provider.checked == [(KEY, "claude-sonnet-5")]

    row = the_row(db, me)
    assert KEY not in row.llm_key_ciphertext
    assert "x" * 40 not in row.llm_key_ciphertext
    assert crypto.decrypt(row.llm_key_ciphertext, user_id=me.id) == KEY
    assert row.llm_key_set_at.tzinfo is not None
    # And a later GET shows what the PUT answered.
    assert read(signed_in) == response.json()


def test_the_plain_key_never_reaches_the_database(signed_in, llm_keyring, fake_provider, db):
    with sql_statements(db) as sent:
        assert put_key(signed_in).status_code == 200

    assert any("user_settings" in line for line in sent)
    # Not the key, nor the 40 characters in the middle of it.
    assert not any("x" * 40 in line for line in sent)


def test_the_model_defaults_to_claude_opus_5(signed_in, llm_keyring, fake_provider):
    response = signed_in.put("/settings/llm", json={"api_key": KEY})

    assert response.status_code == 200
    assert response.json()["model"] == "claude-opus-5"
    assert fake_provider.checked == [(KEY, "claude-opus-5")]


def test_the_key_is_stripped_before_it_is_checked(signed_in, llm_keyring, fake_provider):
    response = put_key(signed_in, f"  {KEY}\n")

    assert response.status_code == 200
    assert response.json()["key_hint"] == "WXYZ"
    assert fake_provider.checked == [(KEY, "claude-opus-5")]


def test_a_new_key_replaces_the_old_one(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)
    service.mark_status(db, me, "rejected")
    # Held across the second save, so the old row is still in the session's identity map
    # when the upsert returns it. The answer must show what the upsert wrote over it.
    earlier = the_row(db, me)

    response = put_key(signed_in, OTHER_KEY, model="claude-haiku-4-5")

    assert response.status_code == 200
    body = response.json()
    assert (body["key_hint"], body["model"], body["status"]) == ("ABCD", "claude-haiku-4-5", "ok")
    assert (earlier.llm_key_hint, earlier.llm_key_status) == ("ABCD", "ok")
    rows = db.scalars(select(UserSettings).where(UserSettings.user_id == me.id)).all()
    assert len(rows) == 1
    assert service.key_for(db, me) == (OTHER_KEY, "claude-haiku-4-5")


@pytest.mark.parametrize(
    "api_key",
    [
        pytest.param("sk-ant-api03-" + "x" * 284 + "WXYZ", id="301-characters"),
        pytest.param("sk-proj-" + "x" * 40 + "WXYZ", id="not-sk-ant"),
        # An Admin API key manages a whole organisation: never one to hold.
        pytest.param("sk-ant-admin01-" + "x" * 40 + "WXYZ", id="admin-key"),
        pytest.param("sk-ant-api03-WXYZ", id="too-short"),
        pytest.param("sk-ant-api03-" + "x" * 20 + " " + "x" * 20, id="inner-space"),
    ],
)
def test_a_malformed_key_is_refused_without_echoing_it(
    signed_in, llm_keyring, fake_provider, db, me, api_key
):
    response = put_key(signed_in, api_key)

    assert response.status_code == 422
    assert response.json() == {"detail": FORMAT_MESSAGE}
    assert api_key not in response.text
    assert fake_provider.checked == []
    assert the_row(db, me) is None


@pytest.mark.parametrize(
    "sent",
    [
        # FastAPI's own 422 would quote the whole body back, key and all...
        pytest.param({"json": {"apiKey": KEY}}, id="misspelt-field"),
        # ...or the value that is not a string...
        pytest.param({"json": {"api_key": 12345678901234567890}}, id="not-a-string"),
        # ...or the raw body, which it tries to read as the model.
        pytest.param({"content": KEY, "headers": {"content-type": "text/plain"}}, id="not-json"),
    ],
)
def test_a_body_that_fails_validation_is_not_echoed(
    signed_in, llm_keyring, fake_provider, db, me, sent
):
    response = signed_in.put("/settings/llm", **sent)

    assert response.status_code == 422
    assert response.json() == {"detail": "The request was not understood"}
    assert response.headers.get("cache-control") == "no-store"
    assert "x" * 40 not in response.text
    assert "12345678901234567890" not in response.text
    assert fake_provider.checked == []
    assert the_row(db, me) is None


def test_other_routes_keep_fastapis_own_422(signed_in):
    # A sibling under /settings: the fixed answer is for /settings/llm alone.
    response = signed_in.patch("/settings/reminders", json={"slot": "breakfast"})

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            {
                "type": "missing",
                "loc": ["body", "reminder_on"],
                "msg": "Field required",
                "input": {"slot": "breakfast"},
            }
        ]
    }


def test_a_model_not_on_the_list_is_refused(signed_in, llm_keyring, fake_provider, db, me):
    response = put_key(signed_in, model="claude-3-opus")

    assert response.status_code == 422
    assert response.json() == {"detail": "Choose one of the listed models"}
    assert fake_provider.checked == []
    assert the_row(db, me) is None


def test_a_refused_key_leaves_the_earlier_one(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)
    fake_provider.error = KeyRejected()

    response = put_key(signed_in, OTHER_KEY)

    assert response.status_code == 422
    assert response.json() == {"detail": "Anthropic refused this key"}
    assert OTHER_KEY not in response.text
    assert fake_provider.checked == [(KEY, "claude-opus-5"), (OTHER_KEY, "claude-opus-5")]
    kept = read(signed_in)
    assert (kept["key_hint"], kept["status"]) == ("WXYZ", "ok")
    assert service.key_for(db, me) == (KEY, "claude-opus-5")


def test_a_model_the_account_cannot_use_is_named(signed_in, llm_keyring, fake_provider, db, me):
    fake_provider.error = ModelUnavailable()

    response = put_key(signed_in, model="claude-haiku-4-5")

    assert response.status_code == 422
    assert response.json() == {"detail": "Your Anthropic account can't use Claude Haiku 4.5"}
    assert the_row(db, me) is None


@pytest.mark.parametrize("error", [ProviderUnavailable, NoCredit])
def test_an_unreachable_anthropic_saves_nothing(
    signed_in, llm_keyring, fake_provider, db, me, error
):
    fake_provider.error = error()

    response = put_key(signed_in)

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Couldn't reach Anthropic to check the key. Nothing was saved."
    }
    assert the_row(db, me) is None
    assert read(signed_in)["status"] == "none"


# --- removing --------------------------------------------------------------------------


def test_removing_the_key(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)

    response = signed_in.delete("/settings/llm")

    assert response.status_code == 204
    assert response.content == b""
    assert read(signed_in)["status"] == "none"
    # The row stays, with every key column empty.
    row = the_row(db, me)
    assert (
        row.llm_provider,
        row.llm_model,
        row.llm_key_ciphertext,
        row.llm_key_hint,
        row.llm_key_status,
        row.llm_key_set_at,
    ) == (None, None, None, None, None, None)
    # And removing it again is no error.
    assert signed_in.delete("/settings/llm").status_code == 204


def test_removing_a_key_that_was_never_saved(signed_in, db, me):
    assert signed_in.delete("/settings/llm").status_code == 204
    assert the_row(db, me) is None


def test_a_key_can_be_removed_from_a_server_without_a_keyring(
    signed_in, llm_keyring, fake_provider, set_keyring
):
    put_key(signed_in)
    set_keyring()

    assert signed_in.delete("/settings/llm").status_code == 204
    assert read(signed_in)["status"] == "none"


# --- whose key -------------------------------------------------------------------------


def test_each_user_sees_only_their_own_key(signed_in, llm_keyring, fake_provider, monkeypatch):
    put_key(signed_in)

    sign_in_as(signed_in, monkeypatch, "sub-other", "other@example.com")
    assert read(signed_in)["status"] == "none"
    assert put_key(signed_in, OTHER_KEY).json()["key_hint"] == "ABCD"
    assert signed_in.delete("/settings/llm").status_code == 204

    sign_in_as(signed_in, monkeypatch, "sub-track", "track@example.com")
    mine = read(signed_in)
    assert (mine["key_hint"], mine["status"]) == ("WXYZ", "ok")


def test_no_answer_is_cached(signed_in, llm_keyring, fake_provider):
    answers = [
        signed_in.get("/settings/llm"),
        put_key(signed_in),
        put_key(signed_in, "not-a-key"),
        signed_in.delete("/settings/llm"),
    ]

    assert [answer.status_code for answer in answers] == [200, 200, 422, 204]
    assert [answer.headers.get("cache-control") for answer in answers] == ["no-store"] * 4


def test_a_profile_save_leaves_the_key_alone(signed_in, llm_keyring, fake_provider):
    """A profile save replaces its child tables wholesale; the key is not one of them."""
    assert UserSettings not in profiles.CHILD_MODELS
    assert signed_in.put("/profile", json=PROFILE).status_code == 200
    put_key(signed_in)

    assert signed_in.put("/profile", json=PROFILE).status_code == 200

    after = read(signed_in)
    assert (after["key_hint"], after["status"]) == ("WXYZ", "ok")


# --- the one place a key is decrypted --------------------------------------------------


def test_a_key_under_another_keyring_reads_as_ok_until_it_is_used(
    signed_in, llm_keyring, fake_provider, db, me, set_keyring
):
    put_key(signed_in)
    set_keyring(Fernet.generate_key().decode())

    # A GET never decrypts, so it cannot tell yet.
    assert read(signed_in)["status"] == "ok"

    assert service.key_for(db, me) is None
    assert the_row(db, me).llm_key_status == "unreadable"
    after = signed_in.get("/settings/llm")
    assert after.status_code == 200
    assert after.json()["status"] == "unreadable"


def test_a_key_marked_rejected_is_not_handed_out(signed_in, llm_keyring, fake_provider, db, me):
    put_key(signed_in)

    service.mark_status(db, me, "rejected")

    assert service.key_for(db, me) is None
    assert read(signed_in)["status"] == "rejected"
    with pytest.raises(ValueError, match="unknown key status"):
        service.mark_status(db, me, "maybe")


def test_without_a_keyring_key_for_says_so(db, me, set_keyring):
    set_keyring()

    with pytest.raises(crypto.NotConfigured):
        service.key_for(db, me)


def test_a_key_copied_into_another_users_row_does_not_decrypt(
    signed_in, llm_keyring, fake_provider, db, me
):
    put_key(signed_in)
    other = User(google_sub="sub-other", email="other@example.com", name="Other")
    db.add(other)
    db.flush()
    db.add(
        UserSettings(
            user_id=other.id,
            llm_provider="anthropic",
            llm_model="claude-opus-5",
            llm_key_ciphertext=the_row(db, me).llm_key_ciphertext,
            llm_key_hint="WXYZ",
            llm_key_status="ok",
            llm_key_set_at=datetime.datetime.now(datetime.UTC),
        )
    )
    db.flush()

    assert service.key_for(db, other) is None
    assert the_row(db, other).llm_key_status == "unreadable"
    assert service.key_for(db, me) == (KEY, "claude-opus-5")


# --- boot ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "keyring",
    [
        pytest.param("not-a-fernet-key", id="garbage"),
        pytest.param(Fernet.generate_key().decode() + ",too-short", id="second-key-bad"),
    ],
)
def test_a_malformed_keyring_stops_the_app_at_boot(set_keyring, keyring):
    set_keyring(keyring)

    with (
        pytest.raises(ValueError, match=MALFORMED_KEYRING) as refused,
        TestClient(app),
    ):
        pass

    # Task 1's fixed message, not Fernet's: no part of the keyring is quoted in a boot log.
    for part in keyring.split(","):
        assert part not in str(refused.value)


def test_an_empty_keyring_boots_with_ai_descriptions_off(set_keyring):
    set_keyring()

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
