"""Re-encrypt every stored API key under the first key of LLM_KEY_ENCRYPTION_KEYS, and exit.

Rotating the keyring:

1. Generate a key and put it first: LLM_KEY_ENCRYPTION_KEYS=<new>,<old>. Deploy. New saves
   are encrypted under the new key, and every stored key still decrypts under the old one.
2. Run this script. It re-encrypts each key still under an older key, and checks that
   every key, rotated or not, is bound to its row's user. It runs in one transaction and
   is safe to re-run.
3. Once a run reports "rotated 0", remove the old key from LLM_KEY_ENCRYPTION_KEYS.

A key that no key in the keyring can read, or one bound to another user, is marked
unreadable and left in place. Its owner is asked to enter it again on the AI descriptions
screen.

Rotation protects against a keyring that leaks on its own. If the keyring and a copy of
the database leak together, it is too late: users must revoke their keys at Anthropic.

Usage:
    uv run python -m scripts.rotate_llm_keys
"""

import sys

from app.db import SessionLocal
from app.llm import crypto
from app.llm.service import rotate_all


def main() -> int:
    if not crypto.available():
        print(
            "LLM_KEY_ENCRYPTION_KEYS is not set, so there is no key to rotate to.",
            file=sys.stderr,
        )
        return 1
    with SessionLocal() as db:
        counts = rotate_all(db)
        db.commit()
    print(f"rotated {counts.rotated}, current {counts.current}, unreadable {counts.unreadable}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
