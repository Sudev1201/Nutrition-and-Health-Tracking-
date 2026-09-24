import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.local_time import local_today
from app.meal_slots import OPTIONAL_SLOTS, SLOTS
from app.models.profile import AvoidedFood, FavouriteIngredient
from app.models.user import User
from app.profiles import baseline as baseline_service
from app.profiles import service
from app.weight import service as weight

router = APIRouter(prefix="/profile", tags=["profile"])



class MedicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    # Required, not optional: the levothyroxine window is checked against it, so
    # a medication without a time cannot be reasoned about at all.
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class MealTimeIn(BaseModel):
    slot: str
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    weekend_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    # None keeps the slot's saved setting, which belongs to the Reminders screen: a
    # client that says nothing about it -- the wizard before plan 8, and a PWA still
    # running that bundle -- must not switch every reminder back on. A slot with no
    # saved setting gets the default: on, except the mid-morning snack.
    reminder_on: bool | None = None
    # Defaults to on, so a client that predates the field still describes a
    # five-meal day rather than silently switching every slot off.
    is_enabled: bool = True


class FoodRefIn(BaseModel):
    """A liked or avoided food.

    The UI only offers foods from the database, so `food_id` is always set on
    anything added now — that is what lets the planner act on a preference rather
    than string-matching a name. It stays optional here so rows saved before that
    rule existed still round-trip when the profile is re-saved.
    """

    label: str = Field(min_length=1, max_length=120)
    food_id: uuid.UUID | None = None
    food_kind: str | None = Field(default=None, pattern="^(dish|ingredient)$")


class UsualIntakeIn(BaseModel):
    """One item of a typical day. A food reference with a weight, not free text —
    a description cannot be costed against the food database."""

    slot: str
    label: str = Field(min_length=1, max_length=120)
    food_id: uuid.UUID
    food_kind: str = Field(pattern="^(dish|ingredient)$")
    grams: float = Field(gt=0, le=5000)


class ObservanceIn(BaseModel):
    kind: str
    weekday: int | None = None
    start_date: datetime.date | None = None
    end_date: datetime.date | None = None
    label: str = ""


class ProfileIn(BaseModel):
    sex: str = Field(pattern="^(male|female)$")
    age: int = Field(ge=1, le=120)
    # The energy equations are weight-based, so an implausible weight would
    # silently produce an implausible target rather than an obvious error.
    weight_kg: float = Field(gt=20, le=300)
    activity: str = Field(pattern="^(sedentary|moderate|heavy)$")

    goal: str = Field(pattern="^(lose|maintain|gain)$")
    pace: str | None = Field(default=None, pattern="^(gentle|steady)$")

    diet_type: str
    cereal_dominant: bool = False
    # Selects the iron figure: ICMR's 29 mg averages menstrual loss, so after
    # menopause the IOM figure applies. Ignored -- stored as null -- for a man.
    menstrual_status: str | None = Field(default=None, pattern="^(menstruating|postmenopausal)$")

    conditions: list[str] = []
    medications: list[MedicationIn] = []
    meal_times: list[MealTimeIn] = []
    observances: list[ObservanceIn] = []
    avoided: list[FoodRefIn] = []
    favourites: list[FoodRefIn] = []
    usual_intake: list[UsualIntakeIn] = []


class MedicationOut(BaseModel):
    name: str
    time: str


class MealTimeOut(BaseModel):
    slot: str
    time: str
    weekend_time: str | None
    reminder_on: bool
    is_enabled: bool


class FoodRefOut(BaseModel):
    label: str
    food_id: uuid.UUID | None
    food_kind: str | None


class UsualIntakeOut(BaseModel):
    slot: str
    label: str
    food_id: uuid.UUID
    food_kind: str
    grams: float


class ObservanceOut(BaseModel):
    kind: str
    weekday: int | None
    start_date: datetime.date | None
    end_date: datetime.date | None
    label: str


class ProfileOut(BaseModel):
    sex: str
    age: int
    weight_kg: float
    activity: str
    goal: str
    pace: str | None
    diet_type: str
    cereal_dominant: bool
    menstrual_status: str | None
    conditions: list[str]
    medications: list[MedicationOut]
    meal_times: list[MealTimeOut]
    # A save replaces the whole questionnaire rather than merging, so every field
    # the GET omits is destroyed by the client's next PUT. Anything accepted by
    # ProfileIn has to be returned here or it cannot survive an edit.
    observances: list[ObservanceOut]
    avoided: list[FoodRefOut]
    favourites: list[FoodRefOut]
    usual_intake: list[UsualIntakeOut]


def _hhmm(value) -> str:
    return value.strftime("%H:%M")


def _to_out(db: Session, user: User) -> ProfileOut:
    profile = service.get_profile(db, user)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet")

    return ProfileOut(
        sex=profile.sex,
        age=profile.age,
        weight_kg=profile.weight_kg,
        activity=profile.activity,
        goal=profile.goal,
        pace=profile.pace,
        diet_type=profile.diet_type,
        cereal_dominant=profile.cereal_dominant,
        menstrual_status=profile.menstrual_status,
        conditions=service.get_conditions(db, user),
        medications=[
            MedicationOut(name=item.name, time=_hhmm(item.taken_at))
            for item in service.get_medications(db, user)
        ],
        meal_times=[
            MealTimeOut(
                slot=item.slot,
                time=_hhmm(item.usual_time),
                weekend_time=_hhmm(item.weekend_time) if item.weekend_time else None,
                reminder_on=item.reminder_on,
                is_enabled=item.is_enabled,
            )
            for item in service.get_meal_times(db, user)
        ],
        observances=[
            ObservanceOut(
                kind=item.kind,
                weekday=item.weekday,
                start_date=item.start_date,
                end_date=item.end_date,
                label=item.label,
            )
            for item in service.get_observances(db, user)
        ],
        avoided=[
            FoodRefOut(label=item.label, food_id=item.food_id, food_kind=item.food_kind)
            for item in service.get_preferences(db, user, AvoidedFood)
        ],
        favourites=[
            FoodRefOut(label=item.label, food_id=item.food_id, food_kind=item.food_kind)
            for item in service.get_preferences(db, user, FavouriteIngredient)
        ],
        usual_intake=[
            UsualIntakeOut(
                slot=item.slot,
                label=item.label,
                food_id=item.food_id,
                food_kind=item.food_kind,
                grams=item.grams,
            )
            for item in service.get_usual_intake(db, user)
        ],
    )


@router.get("", response_model=ProfileOut)
def read_profile(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ProfileOut:
    return _to_out(db, user)


def _energy_basis(goal: str, pace: str | None, activity: str) -> tuple[str, str | None, str]:
    """What the energy formula reads from the profile, besides the body itself.

    A pace left over on a maintain goal changes nothing, so it is not a change.
    """
    return goal, pace if goal != "maintain" else None, activity


@router.put("", response_model=ProfileOut)
def save_profile(
    payload: ProfileIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    if payload.goal != "maintain" and payload.pace is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A goal other than maintain needs a pace"
        )

    bad_slots = [item.slot for item in payload.meal_times if item.slot not in SLOTS]
    if bad_slots:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown slots: {bad_slots}")

    # Four or five meals a day means one or two snacks. A day without lunch is a
    # skipped lunch, not a meal-count preference -- and allowing a main meal to
    # be switched off would make an unlogged one impossible to notice.
    disabled_mains = [
        item.slot
        for item in payload.meal_times
        if not item.is_enabled and item.slot not in OPTIONAL_SLOTS
    ]
    if disabled_mains:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"These meals cannot be switched off: {disabled_mains}. "
            "Skip them for a day instead.",
        )

    existing = service.get_profile(db, user)
    previous = (
        _energy_basis(existing.goal, existing.pace, existing.activity)
        if existing is not None
        else None
    )

    service.save_profile(db, user, payload)

    today = local_today(user)
    # A step was read against the old goal; under a new one it says nothing.
    if previous is not None and previous != _energy_basis(
        payload.goal, payload.pace, payload.activity
    ):
        weight.reset_adjustment(db, user, today)
    # The profile's weight is the latest weigh-in, so a changed weight is a weigh-in.
    # That is also how onboarding records the first one the trend starts from.
    if weight.latest_weight(db, user) != payload.weight_kg:
        weight.record_weigh_in(db, user, today, payload.weight_kg)

    db.commit()
    return _to_out(db, user)


class NutrientBaselineOut(BaseModel):
    code: str
    display_name: str
    unit: str
    category: str
    kind: str
    ear: float | None
    rda: float
    tul: float | None
    usual: float
    off_target: bool


class BaselineOut(BaseModel):
    has_usual_intake: bool
    usual_energy_kcal: float | None
    target_energy_kcal: float
    difference_kcal: float | None
    implausible: bool
    note: str | None
    nutrients: list[NutrientBaselineOut]


@router.get("/baseline", response_model=BaselineOut)
def read_baseline(
    date: datetime.date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BaselineOut:
    """What a usual day adds up to, against what the profile calls for."""
    # The day boundary is the user's, not the server's, so the fallback reads
    # their timezone rather than whatever the host happens to be set to.
    result = baseline_service.compute(db, user, date or local_today(user))
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Complete your profile first")
    return BaselineOut(
        **{key: value for key, value in vars(result).items() if key != "nutrients"},
        nutrients=[NutrientBaselineOut(**vars(row)) for row in result.nutrients],
    )
