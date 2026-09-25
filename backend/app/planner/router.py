import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.llm import crypto
from app.llm import service as llm
from app.llm.providers import (
    MODEL_LABELS,
    KeyRejected,
    ModelUnavailable,
    NoCredit,
    Provider,
    ProviderError,
    get_provider,
)
from app.llm.router import NOT_SET_UP
from app.models.user import User
from app.planner import polish, rules, service

router = APIRouter(prefix="/plan", tags=["plan"])

NO_PLAN = "There is no plan for that week yet"
NO_KEY = "Add your Anthropic API key under AI descriptions first"
KEY_REFUSED = "Anthropic refused your saved key. Replace it under AI descriptions."
MODEL_REFUSED = (
    "Your Anthropic account can't use {label}. Choose another model under AI descriptions."
)
NO_CREDIT = "Your Anthropic account has no credit left."
PROVIDER_DOWN = "Couldn't reach Anthropic. Your plan is unchanged."
# On a polish's 200: how many dishes that request stored new text for. main.py's
# CORS exposes it, so the Plan screen, on its own origin, can read it.
DESCRIBED_HEADER = "X-Dishes-Described"


class PlanItemOut(BaseModel):
    id: uuid.UUID
    slot: str
    dish_id: uuid.UUID
    dish_name: str
    portion: str
    locked: bool
    rationale: str | None
    # AI text for the dish, on the user's own key (plan 9): null until asked for.
    # Two separate fields, so a description can never stand in for the dish's
    # name, its portion or the planner's rationale.
    description: str | None
    cooking_note: str | None


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


class PolishIn(BaseModel):
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


def _model_label(db: Session, user: User) -> str:
    """The saved model's name as the AI descriptions screen shows it."""
    model = llm.summary(db, user).model
    return MODEL_LABELS.get(model, model) if model else "this model"


@router.post("/week/polish", response_model=WeekPlanOut)
def polish_week(
    payload: PolishIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    provider: Provider = Depends(get_provider),
) -> WeekPlanOut:
    """Add AI descriptions to the week's dishes, on the user's own Anthropic key.

    The only route that calls a model; generating, reading and re-planning never
    wait on one. It writes `dish_polish` rows and nothing else: a failure rolls
    back every row this request wrote, and the plan is as it was either way.

    The answer is the week, as every plan route answers it, and DESCRIBED_HEADER
    says how many dishes got new text. 0 is still a 200: every dish already had
    text, or the model gave none the guard kept (a refusal, an answer cut off at
    max_tokens, or only refused text), and those dishes stay undescribed.
    """
    _require_sunday(payload.start)
    plan = service.get_plan(db, user, payload.start)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PLAN)
    try:
        described = polish.polish_week(db, user, plan, provider)
    except crypto.NotConfigured as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NOT_SET_UP) from exc
    except polish.NoKey as exc:
        # Looking the key up may have just marked it unreadable. Keep that, so
        # the AI descriptions screen can say so; nothing else has been written.
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, NO_KEY) from exc
    except KeyRejected as exc:
        db.rollback()
        llm.mark_status(db, user, "rejected")
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, KEY_REFUSED) from exc
    except ModelUnavailable as exc:
        db.rollback()
        detail = MODEL_REFUSED.format(label=_model_label(db, user))
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc
    except NoCredit as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, NO_CREDIT) from exc
    except ProviderError as exc:
        # ProviderUnavailable, and anything else the adapter raises in future.
        db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, PROVIDER_DOWN) from exc
    db.commit()
    response.headers[DESCRIBED_HEADER] = str(described)
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
