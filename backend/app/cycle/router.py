import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.cycle import rules, service
from app.db import get_db
from app.local_time import local_today
from app.models.user import User

router = APIRouter(prefix="/cycle", tags=["cycle"])

NOT_ELIGIBLE = "Cycle tracking is for a woman's profile that is not postmenopausal"


class CycleDayOut(BaseModel):
    date: datetime.date
    flow: str | None
    symptoms: list[str]


class NoteOut(BaseModel):
    id: str
    title: str
    body: str
    evidence: str


class ScreeningOut(BaseModel):
    answered_on: datetime.date
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool


class ReferralOut(BaseModel):
    reason: str


class CycleOut(BaseModel):
    eligible: bool
    ineligible_reason: str | None
    enabled: bool
    has_history: bool
    last_period_start: datetime.date | None
    days: list[CycleDayOut]
    screening: ScreeningOut | None
    coaching: list[NoteOut]
    referral: ReferralOut | None


class EnabledIn(BaseModel):
    enabled: bool


class DayIn(BaseModel):
    flow: str | None = Field(default=None, pattern="^(light|medium|heavy)$")
    symptoms: list[str] = []


class ScreeningIn(BaseModel):
    soaks_within_two_hours: bool
    longer_than_seven_days: bool
    large_clots: bool
    flooding: bool
    date: datetime.date | None = None


def _out(view: service.CycleView) -> CycleOut:
    return CycleOut(
        eligible=view.eligible,
        ineligible_reason=view.ineligible_reason,
        enabled=view.enabled,
        has_history=view.has_history,
        last_period_start=view.last_period_start,
        days=[
            CycleDayOut(date=day.date, flow=day.flow, symptoms=sorted(day.symptoms))
            for day in view.days
        ],
        screening=ScreeningOut(**vars(view.screening)) if view.screening is not None else None,
        coaching=[NoteOut(**vars(note)) for note in view.coaching],
        referral=ReferralOut(reason=view.referral) if view.referral is not None else None,
    )


def _read(db: Session, user: User, on_date: datetime.date) -> CycleOut:
    try:
        return _out(service.view(db, user, on_date))
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


def _not_in_the_future(on_date: datetime.date, user: User) -> None:
    if on_date > local_today(user):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A cycle log cannot be dated in the future"
        )


def _refusal(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NoProfile):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first")
    if isinstance(exc, service.NotEligible):
        return HTTPException(status.HTTP_409_CONFLICT, NOT_ELIGIBLE)
    return HTTPException(status.HTTP_409_CONFLICT, "Turn cycle tracking on first")


@router.get("", response_model=CycleOut)
def read_cycle(
    date: datetime.date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    """`date` is the client's today: coaching such as "days 1-3" is read against it."""
    return _read(db, user, date or local_today(user))


@router.patch("", response_model=CycleOut)
def set_enabled(
    payload: EnabledIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    try:
        service.set_enabled(db, user, payload.enabled)
    except (service.NoProfile, service.NotEligible) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def erase(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    service.erase(db, user)
    db.commit()


@router.put("/days/{on_date}", response_model=CycleOut)
def save_day(
    on_date: datetime.date,
    payload: DayIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    _not_in_the_future(on_date, user)
    unknown = sorted(set(payload.symptoms) - set(rules.SYMPTOMS))
    if unknown:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown symptoms: {unknown}")
    try:
        service.save_day(db, user, on_date, payload.flow, payload.symptoms)
    except (service.NoProfile, service.NotEligible, service.NotEnabled) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))


@router.delete("/days/{on_date}", status_code=status.HTTP_204_NO_CONTENT)
def clear_day(
    on_date: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not service.clear_day(db, user, on_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nothing logged on that date")
    db.commit()


@router.post("/screening", response_model=CycleOut)
def answer_screening(
    payload: ScreeningIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CycleOut:
    on_date = payload.date or local_today(user)
    _not_in_the_future(on_date, user)
    try:
        service.save_screening(
            db,
            user,
            on_date,
            soaks_within_two_hours=payload.soaks_within_two_hours,
            longer_than_seven_days=payload.longer_than_seven_days,
            large_clots=payload.large_clots,
            flooding=payload.flooding,
        )
    except (service.NoProfile, service.NotEligible, service.NotEnabled) as exc:
        raise _refusal(exc) from exc
    db.commit()
    return _read(db, user, local_today(user))
