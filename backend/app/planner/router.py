import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.user import User
from app.planner import rules, service

router = APIRouter(prefix="/plan", tags=["plan"])


class PlanItemOut(BaseModel):
    id: uuid.UUID
    slot: str
    dish_id: uuid.UUID
    dish_name: str
    portion: str
    locked: bool
    rationale: str | None


class PlanDayOut(BaseModel):
    date: datetime.date
    weekday: str
    vegetarian: bool
    vegetarian_reason: str | None
    items: list[PlanItemOut]


class WeekPlanOut(BaseModel):
    start_date: datetime.date
    days: list[PlanDayOut]


class RegenerateIn(BaseModel):
    start: datetime.date


class LockIn(BaseModel):
    locked: bool


class CookingOverlapOut(BaseModel):
    slot: str
    dish_name: str
    members: list[str]


class CookingViewOut(BaseModel):
    date: datetime.date
    overlaps: list[CookingOverlapOut]


def _week_out(db: Session, user: User, plan) -> WeekPlanOut:
    view = service.describe_week(db, user, plan)
    return WeekPlanOut(
        start_date=view.start_date,
        days=[
            PlanDayOut(
                date=day.date,
                weekday=day.weekday,
                vegetarian=day.vegetarian,
                vegetarian_reason=day.vegetarian_reason,
                items=[PlanItemOut(**vars(item)) for item in day.items],
            )
            for day in view.days
        ],
    )


def _require_sunday(start: datetime.date) -> None:
    if rules.sunday_index(start) != 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The plan week starts on a Sunday"
        )


@router.get("/week", response_model=WeekPlanOut)
def read_week(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    """The week's plan, generated and stored the first time it is asked for."""
    _require_sunday(start)
    plan = service.get_plan(db, user, start)
    if plan is None:
        try:
            plan = service.generate_week(db, user, start)
        except service.NoProfile as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
        db.commit()
    return _week_out(db, user, plan)


@router.post("/week/regenerate", response_model=WeekPlanOut)
def regenerate_week(
    payload: RegenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    _require_sunday(payload.start)
    try:
        plan = service.generate_week(db, user, payload.start, reseed=True)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.patch("/items/{item_id}", response_model=WeekPlanOut)
def lock_item(
    item_id: uuid.UUID,
    payload: LockIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    try:
        plan = service.set_locked(db, user, item_id, payload.locked)
    except service.PlanItemNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan item") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.post("/items/{item_id}/swap", response_model=WeekPlanOut)
def swap_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeekPlanOut:
    try:
        plan = service.swap_item(db, user, item_id)
    except service.PlanItemNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such plan item") from exc
    except service.ItemLocked as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Unlock this meal to swap it") from exc
    except service.NoAlternative as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No other dish fits this slot today"
        ) from exc
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _week_out(db, user, plan)


@router.get("/cooking", response_model=CookingViewOut)
def read_cooking(
    date: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CookingViewOut:
    overlaps = service.cooking_view(db, user, date)
    return CookingViewOut(
        date=date,
        overlaps=[CookingOverlapOut(**vars(overlap)) for overlap in overlaps],
    )
