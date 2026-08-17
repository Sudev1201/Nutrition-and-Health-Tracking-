from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.google import GoogleIdentity
from app.models.user import User


def upsert_user_from_identity(db: Session, identity: GoogleIdentity) -> User:
    """Find the user behind a Google identity, creating them on first sign-in.

    Google is the source of truth for email and name, so both are refreshed on
    every sign-in; `google_sub` is the stable key and never changes.
    """
    user = db.scalar(select(User).where(User.google_sub == identity.google_sub))

    if user is None:
        user = User(
            google_sub=identity.google_sub,
            email=identity.email,
            name=identity.name,
        )
        db.add(user)
    else:
        user.email = identity.email
        user.name = identity.name

    db.flush()
    return user
