import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.models.user import User
from app.targets import service

router = APIRouter(prefix="/targets", tags=["targets"])


class NutrientOut(BaseModel):
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    ear: float | None
    rda: float
    tul: float | None
    target_effective: float
    carried_in: float
    carried_from: str | None
    consumed: float


class WarningOut(BaseModel):
    kind: str
    message: str


class TargetsOut(BaseModel):
    date: datetime.date
    nutrients: list[NutrientOut]
    warnings: list[WarningOut]


@router.get("/today", response_model=TargetsOut)
def read_today(
    date: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetsOut:
    resolved = service.resolve_day(db, user, date)
    if resolved is None:
        # No profile yet, so nothing can be computed. The frontend routes this
        # to onboarding rather than showing an error.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first")

    return TargetsOut(
        date=resolved.date,
        nutrients=[NutrientOut(**vars(nutrient)) for nutrient in resolved.nutrients],
        warnings=[WarningOut(kind=w.kind, message=w.message) for w in resolved.warnings],
    )
