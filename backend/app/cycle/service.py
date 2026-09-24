"""Cycle tracking: the switch, logged days, and screening answers.

Nothing in the targets path imports this module, and it imports nothing from
the targets path. The separation is the rule, not an accident of layout: the
iron target already averages menstrual loss and calories do not move with cycle
phase, so cycle data has nothing to tell the targets. `tests/test_cycle_api.py`
checks the imports.
"""

import datetime
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.cycle import rules
from app.models.cycle import CycleLog, CycleScreening, CycleSettings, CycleSymptom
from app.models.profile import Profile
from app.models.user import User
from app.profiles import service as profiles

OWNED = (CycleLog, CycleSymptom, CycleScreening, CycleSettings)


class NoProfile(LookupError):
    """No profile, so no way to know whether tracking applies."""


class NotEligible(ValueError):
    """Tracking is for a woman's profile that is not postmenopausal."""


class NotEnabled(ValueError):
    """Tracking is off, and nothing is logged until it is turned on."""


@dataclass(frozen=True)
class CycleView:
    eligible: bool
    ineligible_reason: str | None  # not-female | postmenopausal
    enabled: bool
    # Rows exist even when hidden -- tracking off, or the profile no longer
    # eligible -- so the screen can still offer to erase them.
    has_history: bool
    last_period_start: datetime.date | None
    days: list[rules.Day]  # newest first
    screening: rules.Screening | None
    coaching: list[rules.Note]
    referral: str | None


def ineligible_reason(profile: Profile) -> str | None:
    if profile.sex != "female":
        return "not-female"
    if profile.menstrual_status == "postmenopausal":
        return "postmenopausal"
    return None


def set_enabled(db: Session, user: User, enabled: bool) -> None:
    profile = _profile(db, user)
    if enabled and ineligible_reason(profile) is not None:
        raise NotEligible
    settings = _settings(db, user)
    if settings is None:
        settings = CycleSettings(user_id=user.id)
        db.add(settings)
    settings.enabled = enabled
    db.flush()


def save_day(
    db: Session, user: User, on_date: datetime.date, flow: str | None, symptoms: list[str]
) -> None:
    """Replace what is logged for one day. No flow and no symptoms clears it."""
    _require_tracking(db, user)
    clear_day(db, user, on_date)
    if flow is not None:
        db.add(CycleLog(user_id=user.id, logged_on=on_date, flow=flow))
    db.add_all(
        [
            CycleSymptom(user_id=user.id, logged_on=on_date, symptom=symptom)
            for symptom in sorted(set(symptoms))
        ]
    )
    db.flush()


def clear_day(db: Session, user: User, on_date: datetime.date) -> bool:
    """Remove a day's log. Allowed whether or not tracking is on: it is the user's data."""
    removed = 0
    for model in (CycleLog, CycleSymptom):
        result = db.execute(
            delete(model).where(model.user_id == user.id, model.logged_on == on_date)
        )
        removed += result.rowcount
    db.flush()
    return removed > 0


def save_screening(
    db: Session,
    user: User,
    on_date: datetime.date,
    *,
    soaks_within_two_hours: bool,
    longer_than_seven_days: bool,
    large_clots: bool,
    flooding: bool,
) -> None:
    _require_tracking(db, user)
    row = db.scalars(
        select(CycleScreening).where(
            CycleScreening.user_id == user.id, CycleScreening.answered_on == on_date
        )
    ).one_or_none()
    if row is None:
        row = CycleScreening(user_id=user.id, answered_on=on_date)
        db.add(row)
    row.soaks_within_two_hours = soaks_within_two_hours
    row.longer_than_seven_days = longer_than_seven_days
    row.large_clots = large_clots
    row.flooding = flooding
    db.flush()


def erase(db: Session, user: User) -> None:
    """Every cycle row the user has, the switch included: back to never having used it."""
    for model in OWNED:
        db.execute(delete(model).where(model.user_id == user.id))
    db.flush()


def view(db: Session, user: User, today: datetime.date) -> CycleView:
    profile = _profile(db, user)
    reason = ineligible_reason(profile)
    settings = _settings(db, user)
    enabled = reason is None and settings is not None and settings.enabled
    has_history = any(
        db.scalar(select(model.id).where(model.user_id == user.id).limit(1)) is not None
        for model in (CycleLog, CycleSymptom, CycleScreening)
    )
    if not enabled:
        # Off means off: the logs are kept, but nothing about them is shown or read.
        return CycleView(
            eligible=reason is None,
            ineligible_reason=reason,
            enabled=False,
            has_history=has_history,
            last_period_start=None,
            days=[],
            screening=None,
            coaching=[],
            referral=None,
        )

    days = _days(db, user, since=today - datetime.timedelta(days=rules.HISTORY_DAYS), until=today)
    screening = _latest_screening(db, user)
    return CycleView(
        eligible=True,
        ineligible_reason=None,
        enabled=True,
        has_history=has_history,
        last_period_start=rules.last_period_start(days),
        days=days,
        screening=screening,
        coaching=rules.coaching(days, today),
        referral=rules.referral_reason(days, screening, today),
    )


def _profile(db: Session, user: User) -> Profile:
    profile = profiles.get_profile(db, user)
    if profile is None:
        raise NoProfile
    return profile


def _settings(db: Session, user: User) -> CycleSettings | None:
    return db.scalars(select(CycleSettings).where(CycleSettings.user_id == user.id)).one_or_none()


def _require_tracking(db: Session, user: User) -> None:
    if ineligible_reason(_profile(db, user)) is not None:
        raise NotEligible
    settings = _settings(db, user)
    if settings is None or not settings.enabled:
        raise NotEnabled


def _days(db: Session, user: User, since: datetime.date, until: datetime.date) -> list[rules.Day]:
    flows = {
        row.logged_on: row.flow
        for row in db.scalars(
            select(CycleLog).where(
                CycleLog.user_id == user.id,
                CycleLog.logged_on >= since,
                CycleLog.logged_on <= until,
            )
        )
    }
    symptoms: dict[datetime.date, set[str]] = defaultdict(set)
    for row in db.scalars(
        select(CycleSymptom).where(
            CycleSymptom.user_id == user.id,
            CycleSymptom.logged_on >= since,
            CycleSymptom.logged_on <= until,
        )
    ):
        symptoms[row.logged_on].add(row.symptom)

    return [
        rules.Day(date=date, flow=flows.get(date), symptoms=frozenset(symptoms.get(date, ())))
        for date in sorted(set(flows) | set(symptoms), reverse=True)
    ]


def _latest_screening(db: Session, user: User) -> rules.Screening | None:
    row = db.scalars(
        select(CycleScreening)
        .where(CycleScreening.user_id == user.id)
        .order_by(CycleScreening.answered_on.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    return rules.Screening(
        answered_on=row.answered_on,
        soaks_within_two_hours=row.soaks_within_two_hours,
        longer_than_seven_days=row.longer_than_seven_days,
        large_clots=row.large_clots,
        flooding=row.flooding,
    )
