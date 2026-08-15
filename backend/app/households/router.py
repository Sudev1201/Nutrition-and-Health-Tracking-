import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.households import service
from app.models.household import Household
from app.models.user import User

router = APIRouter(prefix="/households", tags=["households"])


class CreateHouseholdRequest(BaseModel):
    name: str


class InviteRequest(BaseModel):
    email: EmailStr


class AcceptInviteRequest(BaseModel):
    token: str


class VisibilityRequest(BaseModel):
    share_progress: bool | None = None
    share_health: bool | None = None


class MemberOut(BaseModel):
    user_id: uuid.UUID
    name: str
    email: str
    share_progress: bool
    share_health: bool


class HouseholdOut(BaseModel):
    id: uuid.UUID
    name: str
    members: list[MemberOut]


class InviteOut(BaseModel):
    token: str
    email: str


class MembershipOut(BaseModel):
    share_progress: bool
    share_health: bool


def _to_household_out(db: Session, household: Household) -> HouseholdOut:
    members = []
    for membership in service.list_members(db, household.id):
        member_user = db.get(User, membership.user_id)
        members.append(
            MemberOut(
                user_id=membership.user_id,
                name=member_user.name,
                email=member_user.email,
                share_progress=membership.share_progress,
                share_health=membership.share_health,
            )
        )
    return HouseholdOut(id=household.id, name=household.name, members=members)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=HouseholdOut)
def create_household(
    payload: CreateHouseholdRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdOut:
    try:
        household = service.create_household(db, user, payload.name)
    except service.AlreadyInHousehold as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    db.commit()
    return _to_household_out(db, household)


@router.get("/me", response_model=HouseholdOut)
def read_my_household(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> HouseholdOut:
    household = service.get_household_for_user(db, user)
    if household is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")
    return _to_household_out(db, household)


@router.post("/invites", status_code=status.HTTP_201_CREATED, response_model=InviteOut)
def create_invite(
    payload: InviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteOut:
    household = service.get_household_for_user(db, user)
    if household is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")

    invite = service.invite_member(db, household, payload.email)
    db.commit()
    return InviteOut(token=invite.token, email=invite.email)


@router.post("/invites/accept", response_model=HouseholdOut)
def accept_invite(
    payload: AcceptInviteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdOut:
    try:
        membership = service.accept_invite(db, user, payload.token)
    except service.InviteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except service.InviteExpired as exc:
        raise HTTPException(status.HTTP_410_GONE, str(exc)) from exc
    except service.AlreadyInHousehold as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    db.commit()
    return _to_household_out(db, db.get(Household, membership.household_id))


@router.patch("/visibility", response_model=MembershipOut)
def update_visibility(
    payload: VisibilityRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MembershipOut:
    try:
        membership = service.update_visibility(
            db,
            user,
            share_progress=payload.share_progress,
            share_health=payload.share_health,
        )
    except service.NotInHousehold as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    db.commit()
    return MembershipOut(
        share_progress=membership.share_progress, share_health=membership.share_health
    )
