"""The server's keyring, which encrypts the API keys users bring.

A stored key is a Fernet token (AES-128-CBC with an HMAC-SHA256 over the whole
token, from `cryptography`), so a token whose contents have been altered fails to
open rather than opening to something else. `MultiFernet` over
`LLM_KEY_ENCRYPTION_KEYS` makes the keyring rotatable: the first key encrypts,
and every key decrypts.

The plaintext is `f"{user_id}:{api_key}"`, and `decrypt` checks the prefix. Fernet
has no associated data to bind a token to its row, so the binding travels inside
the ciphertext instead. Someone able to write to the database therefore cannot
copy one user's token onto another user's row and spend the first user's credit:
the copy decrypts, names the wrong user, and is Unreadable.

The keyring is parsed from the setting's current value through an LRU cache
keyed on that value. A test that monkeypatches the setting takes effect at once,
and a malformed keyring raises the moment anything asks for it; the app's
lifespan asks once, so a bad value stops the app at boot.

The key is never derived from `session_secret`. Rotating a leaked session secret
must not make every stored key unreadable, and that secret has a development
default a misconfigured deploy would use without a word.
"""

import functools
import uuid

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import settings

# Fixed messages: nothing raised from here quotes a key, a token or a plaintext.
_NOT_CONFIGURED = "LLM_KEY_ENCRYPTION_KEYS is not set on this server"
_UNREADABLE = "the stored API key cannot be read with this server's keyring"
_MALFORMED = "LLM_KEY_ENCRYPTION_KEYS holds a value that is not a Fernet key"


class NotConfigured(RuntimeError):
    """The server has no keyring: the feature is off."""


class Unreadable(ValueError):
    """Wrong keyring, tampered token, or a token bound to another user."""


def _fernet(entry: str) -> Fernet | None:
    """A Fernet for one keyring entry, or None when the entry is not a Fernet key."""
    try:
        return Fernet(entry)
    except (ValueError, TypeError):
        # Any failure means the entry is not a key. binascii.Error (not base64) and
        # UnicodeError (a non-ASCII character, such as a curly quote) are ValueErrors;
        # TypeError is Fernet's answer to a value that is neither str nor bytes.
        return None


@functools.lru_cache(maxsize=4)
def _fernets(raw: str) -> tuple[Fernet, ...]:
    """One Fernet per comma-separated key, in order. A malformed key raises ValueError."""
    fernets = []
    for part in raw.split(","):
        entry = part.strip()
        if not entry:
            continue
        fernet = _fernet(entry)
        if fernet is None:
            # Raised outside any except block, so no error is chained to it: for a
            # non-ASCII entry, Fernet's error chains one whose .object is the entry.
            raise ValueError(_MALFORMED) from None
        fernets.append(fernet)
    return tuple(fernets)


@functools.lru_cache(maxsize=4)
def _keyring(raw: str) -> MultiFernet | None:
    """The keyring for this setting value, or None when it names no key at all."""
    fernets = _fernets(raw)
    return MultiFernet(fernets) if fernets else None


def _raw() -> str:
    return settings.llm_key_encryption_keys.strip()


def keyring() -> MultiFernet | None:
    """This server's keyring, or None when the feature is off here."""
    return _keyring(_raw())


def available() -> bool:
    """Whether this server can store keys at all."""
    return keyring() is not None


def _require() -> MultiFernet:
    ring = keyring()
    if ring is None:
        raise NotConfigured(_NOT_CONFIGURED)
    return ring


def encrypt(api_key: str, *, user_id: uuid.UUID) -> str:
    """A token for `api_key` that only this user's row can open, under the first key."""
    return _require().encrypt(f"{user_id}:{api_key}".encode()).decode("ascii")


def decrypt(token: str, *, user_id: uuid.UUID) -> str:
    """The API key in `token`, which must have been encrypted for this user.

    NotConfigured rather than Unreadable when there is no keyring: a server
    started without one must not mark every stored key unreadable.
    """
    ring = _require()
    try:
        plaintext = ring.decrypt(token).decode("utf-8")
    except (InvalidToken, ValueError):
        # ValueError: a token that is not ASCII, or a plaintext that is not UTF-8.
        raise Unreadable(_UNREADABLE) from None
    prefix = f"{user_id}:"
    if not plaintext.startswith(prefix):
        raise Unreadable(_UNREADABLE)
    return plaintext.removeprefix(prefix)


def is_current(token: str) -> bool:
    """Whether the first key alone opens `token`, so rotating it would change nothing.

    No user check: this only says which key a token is under. A token no key
    opens is not current, and `rotate` then says it is Unreadable.
    """
    _require()
    newest = _fernets(_raw())[0]
    try:
        newest.decrypt(token)
    except (InvalidToken, ValueError):
        return False
    return True


def rotate(token: str) -> str:
    """`token` re-encrypted under the first key, whichever key it was under.

    The plaintext is carried over untouched, user prefix included. Checking that
    the prefix names the row's user is the caller's job.
    """
    ring = _require()
    try:
        return ring.rotate(token).decode("ascii")
    except (InvalidToken, ValueError):
        raise Unreadable(_UNREADABLE) from None
