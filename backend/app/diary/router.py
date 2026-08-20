import datetime
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.db import get_db
from app.diary import service
from app.models.user import User
from app.profiles import service as profiles

router = APIRouter(prefix="/diary", tags=["diary"])

DEFAULT_SLOT_TIMES = {
    "breakfast": "08:00",
    "snack1": "11:00",
    "lunch": "13:30",
    "snack2": "17:00",
    "dinner": "20:30",
}


class EntryOut(BaseModel):
    id: uuid.UUID
    name: str
    # "½ bowl" — the household measure, which is what the user recognises.
    portion: str
    # Its two parts, so the entry can be reopened in the picker as it was saved.
    measure_name: str | None
    quantity: float | None
    # The absolute the nutrient tables were costed against.
    grams: float | None
    is_estimated: bool
    energy_kcal: float


class SlotOut(BaseModel):
    slot: str
    time: str
    state: str  # logged | empty
    entries: list[EntryOut]


class DiaryOut(BaseModel):
    date: datetime.date
    slots: list[SlotOut]


class NewEntry(BaseModel):
    """A portion, given either as a household measure or as an absolute weight.

    One of the two is required. There is deliberately no default weight: logging
    a portion the user never described is worse than refusing the entry.
    """

    date: datetime.date
    slot: str
    food_id: uuid.UUID
    food_kind: str = Field(pattern="^(dish|ingredient)$")

    measure_name: str | None = Field(default=None, max_length=40)
    quantity: float | None = Field(default=None, gt=0, le=20)

    grams: float | None = Field(default=None, gt=0, le=5000)
    is_estimated: bool = False


class CreatedEntry(BaseModel):
    id: uuid.UUID


@router.get("", response_model=DiaryOut)
def read_diary(
    date: datetime.date = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiaryOut:
    entries = service.list_entries(db, user, date)
    times = {item.slot: item.usual_time.strftime("%H:%M") for item in profiles.get_meal_times(db, user)}

    slots = []
    for slot in service.SLOTS:
        in_slot = [entry for entry in entries if entry.slot == slot]
        slots.append(
            SlotOut(
                slot=slot,
                time=times.get(slot, DEFAULT_SLOT_TIMES[slot]),
                state="logged" if in_slot else "empty",
                entries=[
                    EntryOut(
                        id=entry.id,
                        name=service.entry_name(db, entry),
                        portion=entry.portion_label,
                        measure_name=entry.measure_name,
                        quantity=entry.quantity,
                        grams=entry.grams,
                        is_estimated=entry.is_estimated,
                        energy_kcal=service.entry_nutrients(db, entry).get("energy", 0.0),
                    )
                    for entry in in_slot
                ],
            )
        )

    return DiaryOut(date=date, slots=slots)


@router.post("/entries", status_code=status.HTTP_201_CREATED, response_model=CreatedEntry)
def create_entry(
    payload: NewEntry,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CreatedEntry:
    if payload.slot not in service.SLOTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown slot {payload.slot!r}"
        )

    try:
        grams, label, approximate = service.resolve_portion(
            db,
            food_id=payload.food_id,
            food_kind=payload.food_kind,
            measure_name=payload.measure_name,
            quantity=payload.quantity,
            grams=payload.grams,
        )
    except service.UnknownMeasure as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        entry = service.add_entry(
            db,
            user,
            on_date=payload.date,
            slot=payload.slot,
            food_id=payload.food_id,
            food_kind=payload.food_kind,
            portion_label=label,
            measure_name=payload.measure_name,
            quantity=payload.quantity,
            grams=grams,
            # A generic measure's weight is a general figure, not one measured for
            # this food, so intake logged with it is estimated by definition.
            is_estimated=payload.is_estimated or approximate,
        )
    except service.FoodNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    db.commit()
    return CreatedEntry(id=entry.id)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    if not service.delete_entry(db, user, entry_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such entry")
    db.commit()
