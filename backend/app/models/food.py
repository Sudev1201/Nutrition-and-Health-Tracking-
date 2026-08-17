import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TimestampedBase


class Ingredient(TimestampedBase):
    __tablename__ = "ingredients"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(16))  # IFCT | USDA | manual
    food_group: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # From IFCT's own `tags` column: "vegetarian eggetarian fishetarian veg".
    # Drives diet-type filtering and observance days.
    diet_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # "high" marks greens whose calcium is largely unavailable (palak, arai
    # keerai, colocasia); "low" marks murungai keerai, curry leaf, methi.
    # Spec research: spinach calcium absorption ~5% vs milk ~28-32%.
    oxalate_class: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Regional names from IFCT's `lang` column, so "keerai" finds amaranth.
    search_aliases: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngredientNutrient(TimestampedBase):
    __tablename__ = "ingredient_nutrients"
    __table_args__ = (
        UniqueConstraint("ingredient_id", "nutrient_id", name="uq_ingredient_nutrient"),
    )

    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    # Always in the nutrient's canonical unit, per 100 g of edible portion.
    per_100g: Mapped[float] = mapped_column(Float)
    # "IFCT" | "USDA" | "derived:plant-b12-zero" (see etl/load_usda.py) —
    # widened from 16 to fit the derived-value tag.
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Dish(TimestampedBase):
    __tablename__ = "dishes"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    source: Mapped[str] = mapped_column(String(16))  # authored | INDB | user

    # Authored dishes have a recipe you can open and adjust. INDB reference
    # dishes carry fixed nutrients with no ingredient breakdown, so they are
    # not editable and count as estimated intake.
    is_editable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    slot_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)
    diet_tags: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # Cooked weight / raw ingredient weight. Rice absorbs water (>1), a dosa
    # loses it (<1). Used to express recipe totals per 100 g as served.
    yield_factor: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Null for seed dishes; set for user-created ones. Deliberately NOT keyed
    # to a household — see the spec: dishes follow their author, so a solo
    # user's recipes survive joining or leaving a household.
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )


class DishIngredient(TimestampedBase):
    __tablename__ = "dish_ingredients"

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    grams: Mapped[float] = mapped_column(Float)


class DishNutrient(TimestampedBase):
    """Fixed per-100g nutrients for dishes with no recipe (INDB imports)."""

    __tablename__ = "dish_nutrients"
    __table_args__ = (UniqueConstraint("dish_id", "nutrient_id", name="uq_dish_nutrient"),)

    dish_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), index=True
    )
    nutrient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("nutrients.id", ondelete="CASCADE"), index=True
    )
    per_100g: Mapped[float] = mapped_column(Float)


class PortionMeasure(TimestampedBase):
    """A household measure — "1 idli", "1 tea cup" — and its gram weight."""

    __tablename__ = "portion_measures"

    dish_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dishes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"), nullable=True,
        index=True,
    )
    measure_name: Mapped[str] = mapped_column(String(60))
    grams: Mapped[float] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
