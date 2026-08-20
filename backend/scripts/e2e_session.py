"""Mint a real session for the end-to-end run, and print it as JSON.

The Playwright walk goes through the real backend, real database and real
endpoints -- that is the whole point of having it, since against mocks it would
only assert that the mocks return what they were told. But it cannot go through
Google sign-in, and the frontend's demo-auth handler is no help either: it fakes
`/auth/me` in the browser while the backend still has no session, so every real
endpoint would answer 401.

So this creates (or reuses) a throwaway user and signs a genuine session token
with the app's own code. Nothing about auth is stubbed; the browser simply starts
out already holding a valid cookie, exactly as it would after signing in.

Usage:
    uv run python -m scripts.e2e_session [--reset]

`--reset` deletes the user's profile and diary rows so a run starts from
onboarding. It never touches any user but this one.
"""

import argparse
import json
import sys

from sqlalchemy import delete, select

from app.auth.session import create_session_token
from app.config import settings
from app.db import SessionLocal
from app.models.diary import MealLog, MealSlotSkip
from app.models.profile import (
    AvoidedFood,
    FavouriteIngredient,
    HealthCondition,
    MealSlotTime,
    Medication,
    ObservanceRule,
    Profile,
    UsualIntakeItem,
)
from app.models.user import User

# Recognisable in a database dump, and unmistakably not a real person.
E2E_GOOGLE_SUB = "e2e-playwright-user"
E2E_EMAIL = "e2e@playwright.invalid"

OWNED_MODELS = (
    MealLog,
    MealSlotSkip,
    HealthCondition,
    Medication,
    MealSlotTime,
    ObservanceRule,
    AvoidedFood,
    FavouriteIngredient,
    UsualIntakeItem,
    Profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="clear this user's profile and diary so the run starts at onboarding",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalars(select(User).where(User.google_sub == E2E_GOOGLE_SUB)).one_or_none()
        if user is None:
            user = User(
                google_sub=E2E_GOOGLE_SUB,
                email=E2E_EMAIL,
                name="Playwright",
                timezone="Asia/Kolkata",
            )
            db.add(user)
            db.flush()

        if args.reset:
            # Scoped to this user by id in every statement. A broader delete here
            # would be capable of wiping a real development database.
            for model in OWNED_MODELS:
                db.execute(delete(model).where(model.user_id == user.id))

        token = create_session_token(str(user.id))
        db.commit()

        print(
            json.dumps(
                {
                    "token": token,
                    "cookie_name": settings.session_cookie_name,
                    "user_id": str(user.id),
                }
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
