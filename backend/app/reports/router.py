"""The weekly report over HTTP."""

import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.local_time import local_today
from app.models.user import User
from app.planner import rules
from app.planner import service as planner
from app.reports import service, summary

router = APIRouter(prefix="/reports", tags=["reports"])


class SlotsOut(BaseModel):
    logged: int
    skipped: int
    # The slots enabled now, on every day that has ended. Whatever is neither
    # logged nor skipped was missed.
    expected: int


class PlanAdherenceOut(BaseModel):
    planned: int
    followed: int


class ReportDayOut(BaseModel):
    date: datetime.date
    weekday: str
    state: str  # tracked | untracked | in-progress | future
    energy_kcal: int
    target_kcal: int


class NutrientWeekOut(BaseModel):
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    measured_days: int
    target_total: float
    ear_total: float | None
    consumed_total: float
    days_met: int
    days_over_limit: int
    coverage: float


class GapOut(BaseModel):
    code: str
    display_name: str
    unit: str
    amount: float
    reason_code: str  # not_compensable | cap
    reason: str


class SuggestedFoodOut(BaseModel):
    food_id: uuid.UUID
    name: str


class SuggestionOut(BaseModel):
    nutrient_code: str
    display_name: str
    text: str
    foods: list[SuggestedFoodOut]


class WeeklyReportOut(BaseModel):
    start_date: datetime.date
    end_date: datetime.date
    status: str  # complete | in-progress
    tracked_days: int
    slots: SlotsOut
    measured_kcal: int
    estimated_kcal: int
    plan: PlanAdherenceOut | None
    days: list[ReportDayOut]
    nutrients: list[NutrientWeekOut]
    uncompensated: list[GapOut]
    suggestions: list[SuggestionOut]


def _amount(value: float) -> float:
    return round(value, 1)


def _nutrient_out(week: summary.NutrientWeek) -> NutrientWeekOut:
    return NutrientWeekOut(
        code=week.code,
        display_name=week.display_name,
        unit=week.unit,
        category=week.category,
        kind=week.kind,
        measured_days=week.measured_days,
        target_total=_amount(week.target_total),
        ear_total=_amount(week.ear_total) if week.ear_total is not None else None,
        consumed_total=_amount(week.consumed_total),
        days_met=week.days_met,
        days_over_limit=week.days_over_limit,
        coverage=round(week.coverage, 2),
    )


def _out(report: service.WeekReport) -> WeeklyReportOut:
    plan = None
    if report.plan_planned is not None and report.plan_followed is not None:
        plan = PlanAdherenceOut(planned=report.plan_planned, followed=report.plan_followed)
    return WeeklyReportOut(
        start_date=report.start_date,
        end_date=report.end_date,
        status=report.status,
        tracked_days=report.tracked_days,
        slots=SlotsOut(
            logged=report.slots_logged,
            skipped=report.slots_skipped,
            expected=report.slots_expected,
        ),
        measured_kcal=round(report.measured_kcal),
        estimated_kcal=round(report.estimated_kcal),
        plan=plan,
        days=[
            ReportDayOut(
                date=day.date,
                weekday=day.weekday,
                state=day.state,
                energy_kcal=round(day.energy_kcal),
                target_kcal=round(day.target_kcal),
            )
            for day in report.days
        ],
        nutrients=[_nutrient_out(week) for week in report.nutrients],
        uncompensated=[
            GapOut(
                code=gap.code,
                display_name=gap.display_name,
                unit=gap.unit,
                amount=_amount(gap.amount),
                reason_code=gap.reason_code,
                reason=gap.reason,
            )
            for gap in report.uncompensated
        ],
        suggestions=[
            SuggestionOut(
                nutrient_code=item.nutrient_code,
                display_name=item.display_name,
                text=item.text,
                foods=[
                    SuggestedFoodOut(food_id=food_id, name=name)
                    for food_id, name in item.foods
                ],
            )
            for item in report.suggestions
        ],
    )


@router.get("/week", response_model=WeeklyReportOut)
def read_week(
    start: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WeeklyReportOut:
    """One week's report, derived from the diary on every request and never stored."""
    if rules.sunday_index(start) != 0:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A report week starts on a Sunday"
        )
    today = local_today(user)
    if start > planner.week_start_for(today):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That week has not started yet")
    try:
        report = service.build_week(db, user, start, today)
    except service.NoProfile as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first") from exc
    return _out(report)
