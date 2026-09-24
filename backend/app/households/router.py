import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.households import service
from app.local_time import local_today
from app.models.household import Household
from app.models.user import User
from app.planner import rules
from app.reports import service as reports

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


class MemberProgressOut(BaseModel):
    user_id: uuid.UUID
    name: str
    is_me: bool
    # Whether this viewer may see the member's counts; always true on your own row.
    shared: bool
    # Counts of days, never a nutrient or a figure. Null when the member does not
    # share progress, or has not set up a profile yet.
    tracked_days: int | None
    nutrient_days_met: int | None
    nutrient_days_measured: int | None


class HouseholdProgressOut(BaseModel):
    start_date: datetime.date
    members: list[MemberProgressOut]


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


def _member_progress_out(
    member: User, is_me: bool, shared: bool, counts: reports.ProgressCounts | None
) -> MemberProgressOut:
    return MemberProgressOut(
        user_id=member.id,
        name=member.name,
        is_me=is_me,
        shared=shared,
        tracked_days=counts.tracked_days if counts is not None else None,
        nutrient_days_met=counts.nutrient_days_met if counts is not None else None,
        nutrient_days_measured=counts.nutrient_days_measured if counts is not None else None,
    )


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


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_household(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        service.leave_household(db, user)
    except service.NotInHousehold as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    db.commit()


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


@router.get("/progress", response_model=HouseholdProgressOut)
def read_progress(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HouseholdProgressOut:
    """Each member's week as counts of days on track, so whoever cooks can see it.

    Counts only, whatever `share_health` says: a target is health data -- a
    1,500 mg sodium cap says hypertension -- so no nutrient and no figure leaves
    the member it belongs to.
    """
    if rules.sunday_index(start) != 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The week starts on a Sunday")
    if start > local_today(user):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That week has not started yet")
    membership = service.get_membership(db, user)
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You are not in a household yet")

    # You first, then everyone else in the order they joined.
    rows = sorted(
        service.list_members(db, membership.household_id),
        key=lambda item: item.user_id != user.id,
    )
    members = []
    for row in rows:
        member = db.get(User, row.user_id)
        is_me = row.user_id == user.id
        shared = is_me or row.share_progress
        counts = None
        if shared:
            # The member's own today: a day still in progress where they are is
            # not a finished day, wherever the viewer is.
            counts = reports.member_progress(db, member, start, local_today(member))
        members.append(_member_progress_out(member, is_me, shared, counts))
    return HouseholdProgressOut(start_date=start, members=members)
