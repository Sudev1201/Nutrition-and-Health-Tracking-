import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.auth.google import InvalidGoogleToken, verify_google_id_token
from app.auth.service import upsert_user_from_identity
from app.auth.session import create_session_token
from app.config import settings
from app.db import get_db
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleSignInRequest(BaseModel):
    credential: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    timezone: str


@router.post("/google", response_model=UserOut)
def sign_in_with_google(
    payload: GoogleSignInRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    try:
        identity = verify_google_id_token(payload.credential)
    except InvalidGoogleToken as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google sign-in failed") from exc

    user = upsert_user_from_identity(db, identity)
    db.commit()

    response.set_cookie(
        key=settings.session_cookie_name,
        value=create_session_token(str(user.id)),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
    )
    return user


@router.get("/me", response_model=UserOut)
def read_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    # The attributes sign-in set it with. From https a bare deletion clears the
    # cookie today, but under a __Host- or __Secure- name a Set-Cookie without
    # Secure is rejected outright, and logout would quietly leave the session.
    response.delete_cookie(
        settings.session_cookie_name,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
