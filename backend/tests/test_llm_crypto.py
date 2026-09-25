"""The keyring that encrypts users' API keys. No database, no network.

A stored key is only as safe as three properties, and each is pinned here:
- it never sits in the clear: the token holds neither the key nor its owner;
- it opens only for its owner, and only intact: a token copied onto another
  user's row, altered, or read under another server's keyring is Unreadable,
  never a wrong key;
- the keyring rotates without a flag day: a new key goes first, old tokens still
  open, and rotate() moves each one onto the new key.
"""

import base64
import uuid

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.llm import crypto

# Shaped like an Anthropic key, and obviously not one.
API_KEY = "sk-ant-api03-" + "x" * 40 + "WXYZ"
OWNER = uuid.UUID("11111111-1111-4111-8111-111111111111")
SOMEONE_ELSE = uuid.UUID("22222222-2222-4222-8222-222222222222")

# Two throwaway server keys, generated fresh for each run; no server uses them.
K1 = Fernet.generate_key().decode()
K2 = Fernet.generate_key().decode()


@pytest.fixture
def use_keyring(monkeypatch):
    """Set the server's keyring to these keys, newest first, for this test only."""

    def use(*keys: str) -> None:
        monkeypatch.setattr(settings, "llm_key_encryption_keys", ",".join(keys))

    return use


def altered(token: str) -> str:
    """The token with one character in the middle of its ciphertext changed."""
    middle = len(token) // 2
    replacement = "B" if token[middle] == "A" else "A"
    return token[:middle] + replacement + token[middle + 1 :]


# --- the round trip ------------------------------------------------------------------


def test_a_key_comes_back_for_its_owner(use_keyring):
    use_keyring(K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert crypto.decrypt(token, user_id=OWNER) == API_KEY


def test_the_token_holds_neither_the_key_nor_its_owner(use_keyring):
    use_keyring(K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert API_KEY not in token
    assert str(OWNER) not in token
    # Nor is it merely encoded: the token's own bytes do not carry the key either.
    raw = base64.urlsafe_b64decode(token)
    assert API_KEY.encode() not in raw
    assert str(OWNER).encode() not in raw


def test_encrypting_the_same_key_twice_gives_two_tokens(use_keyring):
    """Equal tokens would show which users share a key."""
    use_keyring(K1)

    first = crypto.encrypt(API_KEY, user_id=OWNER)
    second = crypto.encrypt(API_KEY, user_id=OWNER)

    assert first != second
    assert crypto.decrypt(first, user_id=OWNER) == API_KEY
    assert crypto.decrypt(second, user_id=OWNER) == API_KEY


# --- what does not open --------------------------------------------------------------


def test_a_token_copied_onto_another_users_row_does_not_open(use_keyring):
    """Write access to the database must not let one user spend another's credit."""
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)

    with pytest.raises(crypto.Unreadable) as excinfo:
        crypto.decrypt(token, user_id=SOMEONE_ELSE)

    assert API_KEY not in str(excinfo.value)
    assert token not in str(excinfo.value)


def test_an_altered_token_does_not_open(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(altered(token), user_id=OWNER)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("not-a-token", id="not-base64"),
        pytest.param("gAAAAAB" + "é" * 20, id="not-ascii"),
    ],
)
def test_something_that_is_not_a_token_does_not_open(use_keyring, token):
    use_keyring(K1)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(token, user_id=OWNER)


def test_a_token_from_another_servers_keyring_does_not_open(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring(K2)

    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(token, user_id=OWNER)


# --- rotation --------------------------------------------------------------------------


def test_a_new_token_is_under_the_first_key(use_keyring):
    use_keyring(K2, K1)

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert crypto.is_current(token)
    assert Fernet(K2).decrypt(token) == f"{OWNER}:{API_KEY}".encode()


def test_rotation_moves_a_token_onto_the_new_key(use_keyring):
    use_keyring(K1)
    old = crypto.encrypt(API_KEY, user_id=OWNER)
    assert crypto.is_current(old)

    # Step one of a rotation: the new key goes first, and the old one stays.
    use_keyring(K2, K1)
    assert crypto.decrypt(old, user_id=OWNER) == API_KEY
    assert not crypto.is_current(old)

    new = crypto.rotate(old)
    assert crypto.is_current(new)
    assert crypto.decrypt(new, user_id=OWNER) == API_KEY
    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(new, user_id=SOMEONE_ELSE)

    # Last step, once every row is current: the old key goes.
    use_keyring(K2)
    assert crypto.decrypt(new, user_id=OWNER) == API_KEY
    with pytest.raises(crypto.Unreadable):
        crypto.decrypt(old, user_id=OWNER)


def test_a_token_no_key_opens_is_not_current_and_cannot_be_rotated(use_keyring):
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring(K2)

    assert not crypto.is_current(token)
    with pytest.raises(crypto.Unreadable):
        crypto.rotate(token)


# --- the setting ---------------------------------------------------------------------


def test_spaces_and_empty_entries_in_the_setting_are_ignored(use_keyring):
    use_keyring(f" {K2} , ,{K1},")

    token = crypto.encrypt(API_KEY, user_id=OWNER)

    assert Fernet(K2).decrypt(token) == f"{OWNER}:{API_KEY}".encode()


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param("not-a-fernet-key", id="not-a-key"),
        pytest.param(K1[:-4], id="truncated"),
        pytest.param(K1[:-1], id="bad-padding"),
        pytest.param(base64.urlsafe_b64encode(b"k" * 16).decode(), id="sixteen-bytes"),
        pytest.param(f"{K1},not-a-fernet-key", id="bad-key-after-a-good-one"),
        # Pasted from a document that curled the quotes around it.
        pytest.param(f"“{K1}”", id="in-curly-quotes"),
        pytest.param(K1[:10] + "é" + K1[11:], id="an-accented-letter"),
    ],
)
def test_a_malformed_keyring_is_refused_without_quoting_it(use_keyring, raw):
    """Loudly, and at boot: the lifespan asks for the keyring once. The message is
    fixed whatever went wrong, and no error chained to it carries the value either."""
    use_keyring(raw)

    with pytest.raises(ValueError) as refused:
        crypto.keyring()

    message = str(refused.value)
    assert message == "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"
    for entry in raw.split(","):
        assert entry not in message
    assert refused.value.__cause__ is None
    assert refused.value.__context__ is None


@pytest.mark.parametrize("raw", [pytest.param("", id="empty"), pytest.param("   ", id="blank")])
def test_without_a_keyring_the_feature_is_off(use_keyring, raw):
    use_keyring(raw)

    assert crypto.keyring() is None
    assert crypto.available() is False


@pytest.mark.parametrize(
    "operation",
    [
        pytest.param(lambda token: crypto.encrypt(API_KEY, user_id=OWNER), id="encrypt"),
        pytest.param(lambda token: crypto.decrypt(token, user_id=OWNER), id="decrypt"),
        pytest.param(crypto.is_current, id="is_current"),
        pytest.param(crypto.rotate, id="rotate"),
    ],
)
def test_without_a_keyring_every_operation_says_so(use_keyring, operation):
    """NotConfigured, not Unreadable: a server started without its keyring must not
    look to the caller as if every stored key had gone bad."""
    use_keyring(K1)
    token = crypto.encrypt(API_KEY, user_id=OWNER)
    use_keyring("")

    with pytest.raises(crypto.NotConfigured):
        operation(token)


def test_a_changed_setting_takes_effect_at_once(use_keyring):
    """The parsed keyring is cached on the setting's value, not captured at import."""
    use_keyring(K1)
    ring = crypto.keyring()
    assert crypto.keyring() is ring

    use_keyring(K2)
    assert crypto.keyring() is not ring

    use_keyring(K1)
    assert crypto.keyring() is ring
    assert crypto.available() is True
