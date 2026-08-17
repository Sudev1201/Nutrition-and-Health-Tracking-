import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.session import InvalidSession, read_session_token
from app.config import settings
from app.db import get_db
from app.models.user import User

_UNAUTHORISED = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise _UNAUTHORISED

    try:
        user_id = uuid.UUID(read_session_token(token))
    except (InvalidSession, ValueError) as exc:
        raise _UNAUTHORISED from exc

    user = db.get(User, user_id)
    if user is None:
        raise _UNAUTHORISED
    return user
