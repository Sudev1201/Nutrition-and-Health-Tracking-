from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class User(TimestampedBase):
    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
