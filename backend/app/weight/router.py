import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.local_time import local_today
from app.models.user import User
from app.weight import service

router = APIRouter(prefix="/weight", tags=["weight"])


class WeighInIn(BaseModel):
    # The same plausibility bounds as the profile's weight: the energy equations
    # are weight-based, so a typo here would quietly skew every target.
    weight_kg: float = Field(gt=20, le=300)
    # Defaults to the user's today. A date lets a missed week be filled in; only a
    # weigh-in dated today re-reads the trend.
    date: datetime.date | None = None


class WeighInOut(BaseModel):
    date: datetime.date
    weight_kg: float


class AdjustmentOut(BaseModel):
    delta_kcal: int
    since: datetime.date
    reason: str


class WeightTrendOut(BaseModel):
    weigh_ins: list[WeighInOut]
    smoothed_kg: float | None
    goal: str
    expected_kg_per_week: float
    observed_kg_per_week: float | None
    calorie_target_kcal: int
    adjustment: AdjustmentOut | None
    note: str | None


def _out(trend: service.Trend) -> WeightTrendOut:
    adjustment = None
    if trend.adjustment is not None:
        adjustment = AdjustmentOut(
            delta_kcal=round(trend.adjustment.delta_kcal),
            since=trend.adjustment.since,
            reason=trend.adjustment.reason,
        )
    return WeightTrendOut(
        weigh_ins=[WeighInOut(date=w.date, weight_kg=w.weight_kg) for w in trend.weigh_ins],
        smoothed_kg=round(trend.smoothed_kg, 1) if trend.smoothed_kg is not None else None,
        goal=trend.goal,
        expected_kg_per_week=round(trend.expected_kg_per_week, 2),
        observed_kg_per_week=(
            round(trend.observed_kg_per_week, 2)
            if trend.observed_kg_per_week is not None
            else None
        ),
        calorie_target_kcal=round(trend.calorie_target_kcal),
        adjustment=adjustment,
        note=trend.note,
    )


@router.get("", response_model=WeightTrendOut)
def read_trend(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> WeightTrendOut:
    try:
        return _out(service.trend(db, user, local_today(user)))
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc


@router.post("", response_model=WeightTrendOut, status_code=status.HTTP_201_CREATED)
def add_weigh_in(
    payload: WeighInIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeightTrendOut:
    today = local_today(user)
    on_date = payload.date or today
    if on_date > today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A weigh-in cannot be dated in the future"
        )
    try:
        # A step moves the target but never rewrites a stored plan: regenerating would
        # throw away the user's swaps. Regenerate on the Plan screen re-sizes portions.
        service.record_weigh_in(db, user, on_date, payload.weight_kg)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    db.commit()
    return _out(service.trend(db, user, today))


@router.delete("/{on_date}", status_code=status.HTTP_204_NO_CONTENT)
def remove_weigh_in(
    on_date: datetime.date,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not service.remove_weigh_in(db, user, on_date):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No weigh-in on that date")
    db.commit()
