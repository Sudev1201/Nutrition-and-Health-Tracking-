from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Nutrient(TimestampedBase):
    """One tracked nutrient, with the compensation policy that applies to it.

    Storing the policy here rather than in code means the compensation engine
    reads it as data, and the spec's research is represented in one place.
    """

    __tablename__ = "nutrients"

    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(8))  # kcal | g | mg | ug
    category: Mapped[str] = mapped_column(String(20))  # macro | mineral | vitamin

    # Can a shortfall be made up over following days?
    is_compensable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # How many days a shortfall may be spread over (0 when not compensable).
    compensation_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Does a harmful surplus warrant reducing following days' targets?
    is_excess_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
