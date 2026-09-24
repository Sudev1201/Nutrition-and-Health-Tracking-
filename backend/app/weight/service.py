"""Weigh-ins, and the calorie recalibration they drive.

The profile's weight is the latest weigh-in. One number rather than two means
protein and the energy formula follow measured weight, as the spec asks, and the
trend starts from the onboarding weight rather than from nothing. Writes go
straight to the profile row -- never through `profiles.save_profile`, which
replaces the whole questionnaire.

Must not import `app.targets.service`: that module reads the offset from here.
"""

import datetime
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.local_time import local_today
from app.models.profile import Profile
from app.models.user import User
from app.models.weight import CalorieAdjustment, WeightLog
from app.nutrition_core import recalibration
from app.nutrition_core.energy import energy_target
from app.profiles import service as profiles

# How much history the weight screen shows. The trend itself reads four weeks.
HISTORY_DAYS = 365

RESET_REASON = (
    "Your goal or activity level changed, so your calorie target starts again from the "
    "formula."
)


class NoProfile(LookupError):
    """No profile, so no weight and no target to speak of."""


@dataclass(frozen=True)
class AdjustmentView:
    delta_kcal: float
    since: datetime.date
    reason: str


@dataclass(frozen=True)
class Trend:
    weigh_ins: list[recalibration.WeighIn]
    smoothed_kg: float | None
    goal: str
    expected_kg_per_week: float
    observed_kg_per_week: float | None
    calorie_target_kcal: float
    # The adjustment in force, when it actually moves today's target.
    adjustment: AdjustmentView | None
    note: str | None


def weigh_ins(
    db: Session, user: User, until: datetime.date | None = None
) -> list[recalibration.WeighIn]:
    """The user's weigh-ins, oldest first."""
    query = select(WeightLog).where(WeightLog.user_id == user.id)
    if until is not None:
        query = query.where(WeightLog.logged_on <= until)
    return [
        recalibration.WeighIn(row.logged_on, row.weight_kg)
        for row in db.scalars(query.order_by(WeightLog.logged_on))
    ]


def latest_weight(db: Session, user: User) -> float | None:
    row = _latest(db, user)
    return row.weight_kg if row is not None else None


def adjustment_on(db: Session, user: User, on_date: datetime.date) -> CalorieAdjustment | None:
    """The adjustment in force on a date: the latest that started on or before it."""
    return db.scalars(
        select(CalorieAdjustment)
        .where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from <= on_date,
        )
        .order_by(CalorieAdjustment.effective_from.desc())
        .limit(1)
    ).first()


def offset_on(db: Session, user: User, on_date: datetime.date) -> float:
    """The kcal offset from the formula in force on a date; 0 when none is."""
    adjustment = adjustment_on(db, user, on_date)
    return adjustment.offset_kcal if adjustment is not None else 0.0


def record_weigh_in(
    db: Session, user: User, on_date: datetime.date, weight_kg: float
) -> CalorieAdjustment | None:
    """Store a weigh-in, and take a recalibration step if the trend now calls for one.

    Returns the step taken, or None. Only a weigh-in dated today that is also the
    newest reads the trend: a step dated earlier would change the target of days
    already over. A weigh-in dated before today fills in history and takes no step
    of its own -- but correcting one the step in force was read from re-reads that
    step, so a typo cannot leave a cut standing.
    """
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile

    existing = _on(db, user, on_date)
    if existing is None:
        db.add(WeightLog(user_id=user.id, logged_on=on_date, weight_kg=weight_kg))
    else:
        existing.weight_kg = weight_kg
    db.flush()

    latest = _latest(db, user)
    profile.weight_kg = latest.weight_kg
    db.flush()

    if latest.logged_on == on_date and on_date == local_today(user):
        # A step already taken today on an earlier figure gives way to this one.
        _drop_step_on(db, user, on_date)
        return _take_step(db, user, profile, on_date)
    if existing is not None:
        _reread_step(db, user, profile, on_date)
    return None


def remove_weigh_in(db: Session, user: User, on_date: datetime.date) -> bool:
    """Delete a weigh-in, and any step taken on the strength of it. False if none."""
    row = _on(db, user, on_date)
    if row is None:
        return False
    db.delete(row)
    _drop_step_on(db, user, on_date)
    db.flush()

    latest = _latest(db, user)
    profile = profiles.get_profile(db, user)
    if profile is not None:
        if latest is not None:
            profile.weight_kg = latest.weight_kg
            db.flush()
        _reread_step(db, user, profile, on_date)
    return True


def reset_adjustment(db: Session, user: User, on_date: datetime.date) -> None:
    """Return the target to the formula from `on_date`, and restart the trend there.

    Weigh-ins from before a goal change were eaten against the old goal, so they
    say nothing about the new one.
    """
    _set(db, user, on_date, kind="reset", offset_kcal=0.0, reason=RESET_REASON)


def trend(db: Session, user: User, today: datetime.date) -> Trend:
    """Everything the weight screen shows, as of the user's today."""
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile

    body = profiles.body_of(profile)
    start = today - datetime.timedelta(days=HISTORY_DAYS)
    history = [w for w in weigh_ins(db, user, until=today) if w.date > start]

    current = adjustment_on(db, user, today)
    offset = current.offset_kcal if current is not None else 0.0
    since = current.effective_from if current is not None else None
    points = recalibration.trend_points(history, as_of=today, since=since)

    formula = energy_target(body, goal=profile.goal, pace=profile.pace)
    target = recalibration.recalibrated_energy(body, formula, offset)

    adjustment = None
    if current is not None and abs(target - formula) >= 1.0:
        adjustment = AdjustmentView(
            delta_kcal=target - formula, since=current.effective_from, reason=current.reason
        )
    stepped_on = since if current is not None and current.kind == "step" else None

    return Trend(
        weigh_ins=history,
        smoothed_kg=recalibration.smoothed_weight(history),
        goal=profile.goal,
        expected_kg_per_week=recalibration.expected_rate(body, profile.goal, profile.pace),
        observed_kg_per_week=recalibration.observed_rate(points),
        calorie_target_kcal=target,
        adjustment=adjustment,
        note=recalibration.trend_note(
            body, profile.goal, profile.pace, offset, points, stepped_on=stepped_on
        ),
    )


def _on(db: Session, user: User, on_date: datetime.date) -> WeightLog | None:
    return db.scalars(
        select(WeightLog).where(WeightLog.user_id == user.id, WeightLog.logged_on == on_date)
    ).one_or_none()


def _latest(db: Session, user: User) -> WeightLog | None:
    return db.scalars(
        select(WeightLog)
        .where(WeightLog.user_id == user.id)
        .order_by(WeightLog.logged_on.desc())
        .limit(1)
    ).first()


def _take_step(
    db: Session, user: User, profile: Profile, as_of: datetime.date
) -> CalorieAdjustment | None:
    current = adjustment_on(db, user, as_of)
    points = recalibration.trend_points(
        weigh_ins(db, user, until=as_of),
        as_of=as_of,
        since=current.effective_from if current is not None else None,
    )
    step = recalibration.next_step(
        profiles.body_of(profile),
        profile.goal,
        profile.pace,
        current.offset_kcal if current is not None else 0.0,
        points,
    )
    if step is None:
        return None
    return _set(
        db,
        user,
        as_of,
        kind="step",
        offset_kcal=step.offset_kcal,
        reason=step.reason,
        expected=step.expected_kg_per_week,
        observed=step.observed_kg_per_week,
    )


def _set(
    db: Session,
    user: User,
    effective_from: datetime.date,
    *,
    kind: str,
    offset_kcal: float,
    reason: str,
    expected: float | None = None,
    observed: float | None = None,
) -> CalorieAdjustment:
    """Upsert the adjustment for a date: one per day, the newest decision winning."""
    row = db.scalars(
        select(CalorieAdjustment).where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from == effective_from,
        )
    ).one_or_none()
    if row is None:
        row = CalorieAdjustment(user_id=user.id, effective_from=effective_from)
        db.add(row)
    row.kind = kind
    row.offset_kcal = offset_kcal
    row.reason = reason
    row.expected_kg_per_week = expected
    row.observed_kg_per_week = observed
    db.flush()
    return row


def _reread_step(
    db: Session, user: User, profile: Profile, on_date: datetime.date
) -> CalorieAdjustment | None:
    """Re-read the step in force at its own date, if `on_date` was in its reading.

    A step is read from every weigh-in in its window, not only the one on its date,
    so correcting or deleting any of them must re-read it -- or a typo would leave
    a cut the remaining weigh-ins no longer support.
    """
    step = db.scalars(
        select(CalorieAdjustment)
        .where(CalorieAdjustment.user_id == user.id)
        .order_by(CalorieAdjustment.effective_from.desc())
        .limit(1)
    ).first()
    if step is None or step.kind != "step" or on_date > step.effective_from:
        return None

    previous = adjustment_on(db, user, step.effective_from - datetime.timedelta(days=1))
    start = step.effective_from - datetime.timedelta(days=recalibration.TREND_WINDOW_DAYS)
    if previous is not None:
        start = max(start, previous.effective_from)
    if on_date < start:
        return None

    as_of = step.effective_from
    db.delete(step)
    db.flush()
    return _take_step(db, user, profile, as_of)


def _drop_step_on(db: Session, user: User, on_date: datetime.date) -> None:
    # Only a step: a reset on the same day is a goal change, which still stands.
    db.execute(
        delete(CalorieAdjustment).where(
            CalorieAdjustment.user_id == user.id,
            CalorieAdjustment.effective_from == on_date,
            CalorieAdjustment.kind == "step",
        )
    )
