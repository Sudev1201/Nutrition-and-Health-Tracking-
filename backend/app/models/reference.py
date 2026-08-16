import uuid

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class RdaReference(TimestampedBase):
    """An ICMR-NIN requirement value for one nutrient and demographic.

    `activity_level` is null for nutrients that do not scale with energy, and
    set for the four energy-scaled B vitamins (thiamine, riboflavin, niacin,
    B6) — the widely quoted ICMR figures are the *moderate* column, so a
    sedentary user given those is over-targeted by roughly 25%.
    """

    __tablename__ = "rda_reference"
    __table_args__ = (
        UniqueConstraint(
            "nutrient_id", "sex", "age_band", "activity_level", name="uq_rda_lookup"
        ),
    )

    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    sex: Mapped[str] = mapped_column(String(8))  # male | female
    age_band: Mapped[str] = mapped_column(String(16))  # 18-59 | 60+
    activity_level: Mapped[str | None] = mapped_column(String(12), nullable=True)

    ear: Mapped[float | None] = mapped_column(Float, nullable=True)
    rda: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai: Mapped[float | None] = mapped_column(Float, nullable=True)

    source: Mapped[str] = mapped_column(String(32))  # ICMR-NIN-2020 | IOM | EFSA


class UpperLimit(TimestampedBase):
    """A tolerable upper limit. Absent rows mean no ceiling was defined —
    ICMR deliberately set none for thiamine, riboflavin, biotin, B12 and
    potassium, so the app must not invent one."""

    __tablename__ = "upper_limits"
    __table_args__ = (UniqueConstraint("nutrient_id", "age_band", name="uq_ul_lookup"),)

    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    age_band: Mapped[str] = mapped_column(String(16), default="adult")
    value: Mapped[float] = mapped_column(Float)

    # True when the limit applies only to supplements, not food. Magnesium's
    # 350 mg UL is supplemental-only — warning on dietary magnesium is a bug.
    supplemental_only: Mapped[bool] = mapped_column(default=False, nullable=False)

    source: Mapped[str] = mapped_column(String(32))
