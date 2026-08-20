import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.foods import measures as measures_service
from app.foods import service
from app.models.user import User
from app.profiles import baseline

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("/search")
def search(
    q: str = Query(min_length=1),
    # Raised from 50: the preference pickers ask for a full set of matches
    # rather than a page, and "chicken" alone spans 44 rows.
    limit: int = Query(default=20, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    # min_length=1 admits a single space, which the service strips to "" -- a
    # "%%" LIKE pattern matching every dish in the database. A blank search is
    # a client bug, so it gets a validation error, not twenty arbitrary rows.
    try:
        return service.search_foods(db, q, limit)
    except service.EmptySearchQuery as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


class CostItem(BaseModel):
    food_id: uuid.UUID
    food_kind: str = Field(pattern="^(dish|ingredient)$")
    grams: float = Field(gt=0, le=5000)


class CostRequest(BaseModel):
    items: list[CostItem] = []


class CostResponse(BaseModel):
    totals: dict[str, float]


@router.post("/nutrients", response_model=CostResponse)
def cost_foods(
    payload: CostRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CostResponse:
    """Total the nutrients in a list of foods.

    Stateless on purpose: the onboarding wizard shows a running total for a usual
    day before there is a profile to attach it to, so the sum has to be
    computable from the items alone.
    """
    return CostResponse(
        totals=baseline.total_nutrients(
            db, [(item.food_id, item.food_kind, item.grams) for item in payload.items]
        )
    )


class MeasureOut(BaseModel):
    name: str
    grams: float
    is_default: bool
    # True when the weight is a general figure rather than one measured for this
    # food. The client shows it, and an entry logged with one is marked estimated.
    is_approximate: bool
    unit: str


class MeasuresOut(BaseModel):
    measures: list[MeasureOut]


@router.get("/{food_kind}/{food_id}/measures", response_model=MeasuresOut)
def read_measures(
    food_kind: str,
    food_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeasuresOut:
    """The household measures offered for one food, largest realism first."""
    if food_kind not in ("dish", "ingredient"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown food kind {food_kind!r}"
        )

    return MeasuresOut(
        measures=[
            MeasureOut(
                name=measure.name,
                grams=measure.grams,
                is_default=measure.is_default,
                is_approximate=measure.is_approximate,
                unit=measure.unit,
            )
            for measure in measures_service.measures_for_food(db, food_id, food_kind)
        ]
    )
